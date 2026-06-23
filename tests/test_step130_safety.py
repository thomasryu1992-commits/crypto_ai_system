from __future__ import annotations

from bridge.research_trading_bridge import decide_trade_action
from trading.paper_engine import build_paper_position, update_position_conservative
from execution.live_guard import run_live_readiness_check


def test_synthetic_data_blocks_trading_policy():
    result = decide_trade_action(
        research={"scenario": "Constructive", "signal_timing": "Early", "allow_long": True},
        trading={"trading_signal": {"signal": "LONG", "confidence": 80}},
        data_health={
            "allow_trading": False,
            "is_synthetic": True,
            "is_fallback": True,
            "problems": ["synthetic_data_source_blocks_trading"],
        },
        risk={"allow_new_position": True, "status": "NORMAL"},
    )
    assert result["final_decision"] == "BLOCK_DATA_HEALTH"
    assert result["allow_order_intent"] is False


def test_conflicting_signal_blocks_order_intent():
    result = decide_trade_action(
        research={"scenario": "Bearish", "signal_timing": "Bearish", "allow_long": False, "allow_short": True, "research_bias": "ALLOW_SHORT_OR_RISK_OFF"},
        trading={"trading_signal": {"signal": "LONG", "confidence": 80}},
        data_health={"allow_trading": True, "is_synthetic": False, "is_fallback": False},
        risk={"allow_new_position": True, "status": "NORMAL"},
    )
    assert result["final_decision"] == "BLOCK_CONFLICTING_SIGNAL"
    assert result["allow_order_intent"] is False


def test_conservative_paper_engine_sl_first_for_long():
    position = build_paper_position("LONG", 100.0, "unit_test")
    candle = {"high": position["take_profit"] + 1, "low": position["stop_loss"] - 1, "close": 100}
    closed, active = update_position_conservative(position, candle)
    assert closed["result"] == "LOSS"
    assert active is None


def test_live_readiness_default_is_blocked():
    readiness = run_live_readiness_check()
    assert readiness["ready"] is False
    assert len(readiness["blockers"]) > 0
