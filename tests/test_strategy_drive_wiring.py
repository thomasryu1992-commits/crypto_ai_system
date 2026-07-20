"""Increment 2 wiring: strategy execution bridge + trading-agent drive branch."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from core.json_io import atomic_write_json
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool
from crypto_ai_system.strategy_factory import strategy_trade_decision as std
from crypto_ai_system.strategy_factory.strategy_execution_bridge import build_strategy_decision_for_cycle
from crypto_ai_system.pipeline.trading_agent import TradingAgent
from crypto_ai_system.pipeline.contracts import CycleEnvelope, PipelineContext

NOW = "2026-07-16T00:00:00Z"


def _spec_dict(sid="S004"):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1", "strategy_id": sid, "strategy_version": "1.0",
        "generation_id": "GEN-001", "strategy_family": "trend_pullback", "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"], "timeframe": "1h", "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": [{"feature": "ma20", "comparison": ">", "value_from": "ma50"}]},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 24},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    }).to_dict()


def _candidate(primary="S004", direction="LONG"):
    return {"status": "ENTRY_CANDIDATE", "direction": direction, "order_candidate_count": 1,
            "matched_strategy_ids": [primary], "matched_strategy_count": 1,
            "primary_strategy_id": primary, "primary_strategy_rule_hash": f"hash_{primary}",
            "strategy_pool_version": "active_strategy_pool.v1"}


def _candles(n=60):
    rows, base = [], 60000.0
    for i in range(n):
        base *= 1.002
        c = base * (1.005 if i % 2 == 0 else 0.997)
        rows.append({"timestamp": f"2026-07-10 {i:02d}:00:00+00:00", "open": c * 0.999,
                     "high": c * 1.004, "low": c * 0.996, "close": c, "volume": 1000 + i})
    return rows


def _wire_artifacts(tmp_path, monkeypatch, *, pool):
    files = {
        "ACTIVE_STRATEGY_POOL_PATH": ("pool.json", pool),
        "MARKET_SNAPSHOT_PATH": ("snap.json", {"symbol": "BTCUSDT", "last_close": 65000.0}),
        "RESEARCH_SIGNAL_PATH": ("rs.json", {"trade_permission": {"allow_long": True, "allow_short": True,
                                                                   "allow_new_position": True, "risk_level": "normal"}}),
        "RISK_STATUS_PATH": ("risk.json", {"allow_new_position": True}),
        # The bridge consumes the validation verdicts (QA fix) — wire them to
        # tmp so the test is hermetic instead of leaking real repo storage.
        "DATA_HEALTH_PATH": ("dh.json", {"allow_trading": True}),
        "MARKET_DATA_PATH": ("md.json", {"candles": _candles()}),
    }
    for attr, (name, payload) in files.items():
        p = tmp_path / name
        atomic_write_json(p, payload)
        monkeypatch.setattr(settings, attr, p, raising=False)


# -- bridge -------------------------------------------------------------------

# P2: the validation verdicts are required inputs to the builder.
_VERDICTS = {"data_health": {"allow_trading": True}, "risk": {"allow_new_position": True}}


def test_bridge_none_without_candidate(tmp_path, monkeypatch):
    _wire_artifacts(tmp_path, monkeypatch, pool=empty_pool())
    assert build_strategy_decision_for_cycle(
        {"status": "NO_ENTRY"}, cycle_id="c1", now=NOW, **_VERDICTS) is None


def test_bridge_none_unknown_primary(tmp_path, monkeypatch):
    _wire_artifacts(tmp_path, monkeypatch, pool=empty_pool())
    assert build_strategy_decision_for_cycle(
        _candidate("S999"), cycle_id="c1", now=NOW, **_VERDICTS) is None


def test_bridge_assembles_decision_with_attribution(tmp_path, monkeypatch):
    pool, _ = add_champion(empty_pool(), _spec_dict("S004"), 0.7, now=NOW)
    _wire_artifacts(tmp_path, monkeypatch, pool=pool)
    decision = build_strategy_decision_for_cycle(
        _candidate("S004"), cycle_id="cycle_1", now=NOW, **_VERDICTS)
    assert decision is not None
    assert decision["direction"] == "LONG"
    assert decision["strategy_id"] == "S004"
    assert decision["source"] == "strategy_factory_router"
    assert decision["entry"] == 65000.0
    # SL/TP derived from the strategy's ATR exit rules on the live ATR.
    assert decision["stop_loss"] is not None and decision["take_profit"] is not None
    assert decision["strategy_entry_evaluation_id"]


def test_bridge_enforces_risk_gate(tmp_path, monkeypatch):
    # In isolation there is no approved paper profile, so the hot-path gate must
    # not approve -> the decision is assembled but order intent is refused.
    pool, _ = add_champion(empty_pool(), _spec_dict("S004"), 0.7, now=NOW)
    _wire_artifacts(tmp_path, monkeypatch, pool=pool)
    decision = build_strategy_decision_for_cycle(
        _candidate("S004"), cycle_id="cycle_1", now=NOW, **_VERDICTS)
    assert decision["allow_order_intent"] is False
    assert std.BLOCK_RISK_GATE in decision["block_reasons"]


# -- trading agent drive branch -----------------------------------------------

def _ctx(routing=None):
    ctx = PipelineContext(cycle=CycleEnvelope(cycle_id="cycle_x", started_at_utc=NOW, stage="paper"))
    if routing is not None:
        ctx.data["strategy_routing"] = routing
    return ctx


def test_agent_maybe_decision_none_without_routing():
    assert TradingAgent()._maybe_strategy_decision(_ctx(), "paper", 0) is None


def test_agent_maybe_decision_none_for_non_candidate():
    assert TradingAgent()._maybe_strategy_decision(_ctx({"status": "NO_ENTRY"}), "paper", 0) is None


def test_agent_maybe_decision_isolated_from_errors(monkeypatch):
    # A malformed routing dict must not raise out of the helper (research path safe).
    result = TradingAgent()._maybe_strategy_decision(_ctx({"status": "ENTRY_CANDIDATE"}), "paper", 0)
    assert result is None or isinstance(result, dict)
