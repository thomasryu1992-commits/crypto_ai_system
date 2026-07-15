"""B-4: the canonical paper position kernel opens from a filled entry and, on
exit (SL/TP/time/manual), produces a CLOSED outcome with a real result_R."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.config import load_config
from crypto_ai_system.execution import paper_position_kernel as kernel
from crypto_ai_system.registry.base_registry import load_registry_records, registry_path


def _cfg(tmp_path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _intent():
    return {
        "side": "BUY",
        "direction": "LONG",
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "quantity": 0.1,
    }


def _reconciliation():
    return {
        "reconciliation_id": "r1",
        "execution_id": "e1",
        "order_intent_id": "oi1",
        "decision_id": "d1",
        "risk_gate_id": "rg1",
        "research_signal_id": "rs1",
        "profile_id": "p1",
        "reconciled": True,
        "reconciliation_mismatch": False,
        "reconciliation_evidence_hash": "hash1",
        "expected_order_intent": _intent(),
        "simulated_fill": {"avg_fill_price": 100.0, "filled_quantity": 0.1, "fill_status": "FILLED"},
    }


def _execution():
    return {
        "execution_id": "e1",
        "order_intent_id": "oi1",
        "decision_id": "d1",
        "risk_gate_id": "rg1",
        "research_signal_id": "rs1",
        "simulated_fill": {"avg_fill_price": 100.0, "filled_quantity": 0.1, "fill_status": "FILLED"},
        "expected_order_intent": _intent(),
    }


def _open(cfg):
    return kernel.open_from_execution(_execution(), _reconciliation(), cycle_id="cyc1", cfg=cfg)


def test_open_from_filled_entry(tmp_path):
    cfg = _cfg(tmp_path)
    pos = _open(cfg)
    assert pos is not None
    assert pos["direction"] == "LONG"
    assert pos["entry_price"] == 100.0
    assert pos["risk"] == 2.0
    assert kernel.has_open_position(cfg) is True


def test_no_open_on_no_fill(tmp_path):
    cfg = _cfg(tmp_path)
    ex = _execution()
    ex["simulated_fill"]["fill_status"] = "NO_FILL"
    assert kernel.open_from_execution(ex, _reconciliation(), cfg=cfg) is None
    assert kernel.has_open_position(cfg) is False


def test_stop_loss_settles_closed_outcome(tmp_path):
    cfg = _cfg(tmp_path)
    _open(cfg)
    result = kernel.settle_open_position(
        {"high": 100.5, "low": 97.0}, last_close=97.5, timeframe="1h", cfg=cfg
    )
    assert result is not None
    assert result["close_reason"] == "stop_loss"
    assert result["result_R"] == -1.0
    assert result["outcome_status"] == "OUTCOME_RECORDED"
    assert kernel.has_open_position(cfg) is False
    # The closed outcome is appended exactly once with the real result_R.
    rows = load_registry_records(registry_path(cfg, "outcome_feedback_registry"))
    closed = [r for r in rows if r.get("outcome_closed") is True]
    assert len(closed) == 1
    assert closed[0]["result_R"] == -1.0
    assert closed[0]["execution_id"] == "e1"


def test_take_profit_settles_win(tmp_path):
    cfg = _cfg(tmp_path)
    _open(cfg)
    result = kernel.settle_open_position(
        {"high": 105.0, "low": 100.0}, last_close=104.0, timeframe="1h", cfg=cfg
    )
    assert result["close_reason"] == "take_profit"
    assert result["result_R"] == 2.0  # (104-100)/2


def test_same_candle_sl_first(tmp_path):
    cfg = _cfg(tmp_path)
    _open(cfg)
    result = kernel.settle_open_position(
        {"high": 105.0, "low": 97.0}, last_close=100.0, timeframe="1h", cfg=cfg
    )
    assert result["close_reason"] == "stop_loss"


def test_time_exit(tmp_path):
    cfg = _cfg(tmp_path)
    pos = _open(cfg)
    pos["holding_candles"] = 47  # next settle -> 48 == max_hold for 1h
    kernel._save_position(cfg, pos)
    result = kernel.settle_open_position(
        {"high": 100.2, "low": 99.8}, last_close=101.0, timeframe="1h", cfg=cfg
    )
    assert result["close_reason"] == "time_exit"
    assert result["result_R"] == 0.5  # (101-100)/2


def test_neutral_candle_keeps_open(tmp_path):
    cfg = _cfg(tmp_path)
    _open(cfg)
    result = kernel.settle_open_position(
        {"high": 100.2, "low": 99.8}, last_close=100.0, timeframe="1h", cfg=cfg
    )
    assert result is None
    assert kernel.has_open_position(cfg) is True


def test_settle_no_position(tmp_path):
    cfg = _cfg(tmp_path)
    assert kernel.settle_open_position({"high": 1, "low": 1}, last_close=1, cfg=cfg) is None
