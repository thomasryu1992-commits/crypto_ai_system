"""holding_candles must count distinct candles, not settle invocations (QA fix):
extra manual pipeline runs within one interval must not accelerate time_exit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution import live_position_kernel as live_kernel
from crypto_ai_system.execution.paper_position_kernel import settle_trade_plan


def _plan():
    return {"direction": "LONG", "entry_price": 100.0, "stop_loss": 90.0,
            "take_profit": 120.0, "risk": 10.0, "holding_candles": 0}


def test_paper_same_candle_counts_once():
    pos = _plan()
    candle = {"timestamp": "2026-07-19T10:00:00+00:00", "high": 101.0, "low": 99.0}
    settle_trade_plan(pos, candle, 100.0, 48, False)
    settle_trade_plan(pos, candle, 100.0, 48, False)  # manual re-run, same candle
    settle_trade_plan(pos, candle, 100.0, 48, False)
    assert pos["holding_candles"] == 1


def test_paper_new_candle_advances_the_count():
    pos = _plan()
    settle_trade_plan(pos, {"timestamp": "T1", "high": 101.0, "low": 99.0}, 100.0, 48, False)
    settle_trade_plan(pos, {"timestamp": "T2", "high": 101.0, "low": 99.0}, 100.0, 48, False)
    assert pos["holding_candles"] == 2


def test_paper_candle_without_timestamp_keeps_legacy_behavior():
    pos = _plan()
    candle = {"high": 101.0, "low": 99.0}  # no timestamp -> per-invocation
    settle_trade_plan(pos, candle, 100.0, 48, False)
    settle_trade_plan(pos, candle, 100.0, 48, False)
    assert pos["holding_candles"] == 2


def test_live_kernel_same_candle_counts_once():
    pos = _plan()
    candle = {"timestamp": "T1", "high": 101.0, "low": 99.0}
    live_kernel._advance_holding(pos, candle)
    live_kernel._advance_holding(pos, candle)
    assert pos["holding_candles"] == 1
    live_kernel._advance_holding(pos, {"timestamp": "T2"})
    assert pos["holding_candles"] == 2
