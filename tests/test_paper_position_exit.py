"""P0-4: active paper positions must be evaluated for exit each cycle.

Before this, ``run_paper_cycle`` only updated the last price for an open
position, so positions never closed and no closed trade was ever collected.
These tests exercise the exit-evaluation helpers directly (hermetic — the
trade sink is stubbed so nothing writes to storage).
"""

from __future__ import annotations

import pytest

from crypto_ai_system.trading import paper_engine
from crypto_ai_system.trading.paper_engine import (
    build_paper_position,
    close_trade,
    evaluate_open_position,
)


@pytest.fixture(autouse=True)
def _no_disk(monkeypatch):
    # close_trade appends to PAPER_TRADES_PATH; keep the unit tests hermetic.
    monkeypatch.setattr(paper_engine, "_save_trade", lambda trade: None)


def _long():
    return build_paper_position("LONG", 100.0, "unit_test")


def _short():
    return build_paper_position("SHORT", 100.0, "unit_test")


def test_stop_loss_hit_closes_as_loss():
    pos = _long()
    candle = {"high": pos["entry_price"] + 1, "low": pos["stop_loss"] - 1, "close": pos["stop_loss"]}
    closed, still_open = evaluate_open_position(pos, candle, last_close=pos["stop_loss"])
    assert still_open is None
    assert closed["result"] == "LOSS"
    assert closed["pnl_r"] == -1.0
    assert closed["exit_reason"] == "stop_loss_pessimistic_first"


def test_take_profit_hit_closes_as_win():
    pos = _long()
    candle = {"high": pos["take_profit"] + 1, "low": pos["entry_price"] - 1, "close": pos["take_profit"]}
    closed, still_open = evaluate_open_position(pos, candle, last_close=pos["take_profit"])
    assert still_open is None
    assert closed["result"] == "WIN"
    assert closed["pnl_r"] > 0


def test_same_candle_sl_and_tp_is_sl_first():
    pos = _long()
    # Candle spans both stop and target -> pessimistic policy takes SL first.
    candle = {"high": pos["take_profit"] + 1, "low": pos["stop_loss"] - 1, "close": pos["entry_price"]}
    closed, still_open = evaluate_open_position(pos, candle, last_close=pos["entry_price"])
    assert still_open is None
    assert closed["result"] == "LOSS"


def test_neutral_candle_keeps_position_open():
    pos = _long()
    candle = {"high": pos["entry_price"] + 0.1, "low": pos["entry_price"] - 0.1, "close": pos["entry_price"]}
    closed, still_open = evaluate_open_position(pos, candle, last_close=pos["entry_price"], max_hold_bars=999)
    assert closed is None
    assert still_open is not None
    assert still_open["holding_candles"] == 1


def test_time_exit_after_max_hold():
    pos = _long()
    candle = {"high": pos["entry_price"] + 0.1, "low": pos["entry_price"] - 0.1, "close": pos["entry_price"]}
    # max_hold_bars=1: update increments holding_candles to 1 -> time exit fires.
    closed, still_open = evaluate_open_position(pos, candle, last_close=101.0, max_hold_bars=1)
    assert still_open is None
    assert closed["exit_reason"] == "time_exit"
    assert closed["result"] == "TIME_EXIT"
    assert closed["pnl_r"] > 0  # exited above entry -> partial win


def test_manual_exit_closes_immediately():
    pos = _long()
    closed, still_open = evaluate_open_position(pos, candle=None, last_close=98.0, manual_exit=True)
    assert still_open is None
    assert closed["exit_reason"] == "manual_exit"
    assert closed["result"] == "MANUAL_EXIT"
    assert closed["pnl_r"] < 0  # exited below entry -> partial loss


def test_time_exit_signed_r_for_short():
    pos = _short()
    # Short exited below entry -> profit.
    closed = close_trade(pos, "TIME_EXIT", 95.0, "time_exit")
    assert closed["pnl_r"] > 0


def test_no_candle_no_manual_keeps_open():
    pos = _long()
    closed, still_open = evaluate_open_position(pos, candle=None, last_close=100.0, max_hold_bars=999)
    assert closed is None
    assert still_open is pos


def test_run_paper_cycle_closes_open_position(monkeypatch):
    """Integration: the legacy Path A run_paper_cycle evaluates an open position
    and closes it. In the active runtime the kernel owns positions, so exercise
    the legacy path explicitly here."""
    monkeypatch.setattr(paper_engine, "KERNEL_OWNS_POSITIONS", False)
    pos = _long()
    state = {"active_position": pos, "closed_trades": []}
    saved = {}

    monkeypatch.setattr(paper_engine, "load_paper_state", lambda: state)
    monkeypatch.setattr(paper_engine, "save_paper_state", lambda s: saved.update(s))
    # TP-hitting candle from the "market data" the cycle reads.
    monkeypatch.setattr(
        paper_engine,
        "_latest_candle",
        lambda: {"high": pos["take_profit"] + 1, "low": pos["entry_price"] - 1, "close": pos["take_profit"]},
    )

    result = paper_engine.run_paper_cycle(
        {"signal": "NONE", "reasons": []},
        {"last_close": pos["take_profit"], "timeframe": "1h"},
        allow_new_position=False,
    )

    assert result["status"] == "POSITION_CLOSED"
    assert result["active_position"] is None
    assert result["closed_trade"]["result"] == "WIN"
    assert saved["active_position"] is None
    assert len(saved["closed_trades"]) == 1
