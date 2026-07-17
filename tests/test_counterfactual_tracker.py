"""The counterfactual tracker shadows blocked signals so an over-conservative
gate becomes measurable, without ever contaminating realized P&L."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.config import load_config
from crypto_ai_system.feedback import counterfactual_tracker as tracker
from crypto_ai_system.registry.base_registry import load_registry_records, registry_path


def _cfg(tmp_path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _snapshot():
    return {
        "last_close": 100.0,
        "atr": 2.0,
        "timeframe": "1h",
        "symbol": "BTCUSDT",
        "trend_bias": "TREND_UP",
    }


def _blocked_decision(**overrides):
    decision = {
        "symbol": "BTCUSDT",
        # Every block forces direction NONE; the tracker must not trust this field.
        "direction": "NONE",
        "final_decision": "BLOCK_RISK",
        "reasons": ["daily_loss_limit_breached"],
        "trading_signal": {"signal": "LONG", "confidence": 70},
        "allow_order_intent": False,
        "research_signal_id": "rs1",
        "decision_id": "d1",
        "profile_id": "p1",
        "risk_gate_id": "rg1",
        "pre_order_risk_gate": {
            "status": "BLOCK_DAILY_LOSS_LIMIT",
            "approved": False,
            "block_reasons": ["daily_loss_limit_gate_blocked"],
            "risk_gate_id": "rg1",
        },
    }
    decision.update(overrides)
    return decision


def _record(cfg, decision=None):
    return tracker.record_blocked_signal(
        decision or _blocked_decision(),
        market_snapshot=_snapshot(),
        research_signal={},
        cycle_id="cyc1",
        cfg=cfg,
    )


def _settle(cfg, candle, last_close):
    return tracker.settle_counterfactuals(
        candle, last_close=last_close, timeframe="1h", regime="TREND_UP", cfg=cfg
    )


def test_records_plan_from_intended_direction(tmp_path):
    cfg = _cfg(tmp_path)
    plan = _record(cfg)
    assert plan is not None
    # The blocked decision reports NONE; the signal wanted LONG, so the plan is LONG.
    assert plan["direction"] == "LONG"
    assert plan["entry_price"] == 100.0
    assert plan["stop_loss"] == 98.0
    assert plan["take_profit"] == 104.0
    assert plan["risk"] == 2.0
    # The gate is the more specific authority when it blocked.
    assert plan["block_stage"] == "pre_order_risk_gate"
    assert plan["block_reason"] == "BLOCK_DAILY_LOSS_LIMIT"
    assert len(tracker.load_open_counterfactuals(cfg)) == 1


def test_falls_back_to_decision_when_gate_did_not_block(tmp_path):
    cfg = _cfg(tmp_path)
    plan = _record(
        cfg,
        _blocked_decision(
            final_decision="BLOCK_CONFLICTING_SIGNAL",
            pre_order_risk_gate={"status": "PASS_PAPER", "approved": True, "block_reasons": []},
        ),
    )
    assert plan["block_stage"] == "trading_decision"
    assert plan["block_reason"] == "BLOCK_CONFLICTING_SIGNAL"


def _suppressed_decision():
    """A block upstream of the bridge: the permission gate has already rewritten
    the side to FLAT/NONE, so only the scenario still carries the view."""
    return _blocked_decision(
        final_decision="BLOCK_RISK",
        trading_signal={"signal": "NONE", "reasons": ["RESEARCH_SIGNAL_NO_DIRECTIONAL_ENTRY"]},
    )


def _record_with_signal(cfg, research_signal, decision=None):
    return tracker.record_blocked_signal(
        decision or _suppressed_decision(),
        market_snapshot=_snapshot(),
        research_signal=research_signal,
        cycle_id="cyc1",
        cfg=cfg,
    )


def test_scenario_recovers_a_view_the_gate_erased(tmp_path):
    """A Risk-Off timing zeroes the permission, which collapses every
    direction-carrying field to FLAT. The bullish view still happened, and the
    block that suppressed it is exactly what needs measuring."""
    cfg = _cfg(tmp_path)
    plan = _record_with_signal(
        cfg, {"scenario": "Bullish", "signal_timing": "Risk-Off", "entry_side": "FLAT"}
    )
    assert plan is not None
    assert plan["direction"] == "LONG"
    assert plan["entry_price"] == 100.0


def test_scenario_recovers_a_short_view(tmp_path):
    cfg = _cfg(tmp_path)
    plan = _record_with_signal(
        cfg, {"scenario": "Bearish", "signal_timing": "Data-Blocked", "entry_side": "FLAT"}
    )
    assert plan["direction"] == "SHORT"


def test_non_directional_scenario_is_nothing_to_miss(tmp_path):
    """Cautious is not a suppressed view — the research simply had no setup."""
    cfg = _cfg(tmp_path)
    assert (
        _record_with_signal(
            cfg, {"scenario": "Cautious", "signal_timing": "Risk-Off", "entry_side": "FLAT"}
        )
        is None
    )
    assert tracker.load_open_counterfactuals(cfg) == []


def test_no_shadow_without_a_direction(tmp_path):
    cfg = _cfg(tmp_path)
    assert _record(cfg, _blocked_decision(trading_signal={"signal": "NONE"})) is None
    assert tracker.load_open_counterfactuals(cfg) == []


def test_no_shadow_for_incoherent_plan(tmp_path):
    cfg = _cfg(tmp_path)
    # A LONG whose stop sits above entry is not a trade we missed; it is garbage.
    decision = _blocked_decision(
        trading_signal={"signal": "LONG", "stop_loss": 105.0, "take_profit": 110.0}
    )
    assert _record(cfg, decision) is None


def test_same_setup_blocked_repeatedly_is_one_shadow(tmp_path):
    cfg = _cfg(tmp_path)
    assert _record(cfg) is not None
    # research_signal_id is a content hash: an unchanged setup re-firing next
    # cycle is the same shadow trade, not a second one.
    assert _record(cfg) is None
    assert len(tracker.load_open_counterfactuals(cfg)) == 1


def test_book_is_capped(tmp_path):
    cfg = _cfg(tmp_path)
    for i in range(tracker.MAX_OPEN_COUNTERFACTUALS + 5):
        _record(cfg, _blocked_decision(research_signal_id=f"rs{i}"))
    assert len(tracker.load_open_counterfactuals(cfg)) == tracker.MAX_OPEN_COUNTERFACTUALS


def test_take_profit_settles_as_missed_opportunity(tmp_path):
    cfg = _cfg(tmp_path)
    _record(cfg)
    settled = _settle(cfg, {"high": 105.0, "low": 100.0}, 104.0)
    assert len(settled) == 1
    outcome = settled[0]
    assert outcome["classification"] == tracker.MISSED_OPPORTUNITY
    assert outcome["result_R"] == 2.0  # (104-100)/2
    assert outcome["close_reason"] == "take_profit"
    assert outcome["block_reason"] == "BLOCK_DAILY_LOSS_LIMIT"
    assert outcome["hypothetical"] is True
    assert tracker.load_open_counterfactuals(cfg) == []


def test_stop_loss_settles_as_avoided_loss(tmp_path):
    cfg = _cfg(tmp_path)
    _record(cfg)
    settled = _settle(cfg, {"high": 100.5, "low": 97.0}, 97.5)
    assert settled[0]["classification"] == tracker.AVOIDED_LOSS
    assert settled[0]["result_R"] == -1.0


def test_short_settles_with_kernel_math(tmp_path):
    cfg = _cfg(tmp_path)
    plan = _record(cfg, _blocked_decision(trading_signal={"signal": "SHORT"}))
    assert plan["direction"] == "SHORT"
    assert plan["stop_loss"] == 102.0
    assert plan["take_profit"] == 96.0
    settled = _settle(cfg, {"high": 100.0, "low": 95.0}, 96.0)
    assert settled[0]["close_reason"] == "take_profit"
    assert settled[0]["result_R"] == 2.0  # (100-96)/2


def test_same_candle_stop_first_matches_paper_kernel(tmp_path):
    cfg = _cfg(tmp_path)
    _record(cfg)
    settled = _settle(cfg, {"high": 105.0, "low": 97.0}, 100.0)
    assert settled[0]["close_reason"] == "stop_loss"


def test_neutral_candle_keeps_shadow_open(tmp_path):
    cfg = _cfg(tmp_path)
    _record(cfg)
    assert _settle(cfg, {"high": 100.2, "low": 99.8}, 100.0) == []
    open_rows = tracker.load_open_counterfactuals(cfg)
    assert len(open_rows) == 1
    assert open_rows[0]["holding_candles"] == 1


def test_settled_outcome_lands_in_its_own_registry(tmp_path):
    cfg = _cfg(tmp_path)
    _record(cfg)
    _settle(cfg, {"high": 105.0, "low": 100.0}, 104.0)
    rows = load_registry_records(
        registry_path(cfg, tracker.COUNTERFACTUAL_OUTCOME_REGISTRY_NAME)
    )
    assert len(rows) == 1
    assert rows[0]["counterfactual_outcome_id"]
    assert rows[0]["research_signal_id"] == "rs1"


def test_hypothetical_outcome_never_reaches_realized_pnl(tmp_path):
    """The risk guard computes its loss limits from outcome_feedback_registry.
    A trade that never happened must not appear there, or the gates would start
    reacting to imaginary P&L."""
    cfg = _cfg(tmp_path)
    _record(cfg)
    _settle(cfg, {"high": 105.0, "low": 100.0}, 104.0)
    realized = registry_path(cfg, "outcome_feedback_registry")
    assert not realized.exists() or load_registry_records(realized) == []


def test_settle_with_empty_book_is_a_noop(tmp_path):
    cfg = _cfg(tmp_path)
    assert _settle(cfg, {"high": 105.0, "low": 95.0}, 100.0) == []
