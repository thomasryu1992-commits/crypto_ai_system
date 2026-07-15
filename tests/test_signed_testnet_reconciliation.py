"""Tests for signed-testnet reconciliation (mocked adapter, no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution.signed_testnet_reconciliation import (
    reconcile_signed_testnet,
)


class _MockAdapter:
    def __init__(self, order, positions, balance):
        self._order = order
        self._positions = positions
        self._balance = balance

    def query_order(self, symbol, client_order_id):
        return self._order

    def get_positions(self, symbol=None):
        return self._positions

    def get_balance(self):
        return self._balance


def _order_result(submitted=True, qty=0.001, side="BUY"):
    return {
        "external_order_submission_performed": submitted,
        "exchange_order_id": 555,
        "client_order_id": "CAI_BTCUSDT_LONG_x",
        "intent": {"symbol": "BTCUSDT", "side": side, "quantity": qty},
    }


def _ok(response):
    return {"ok": True, "response": response}


def _filled_order(qty="0.001"):
    return _ok({"orderId": 555, "status": "FILLED", "executedQty": qty, "avgPrice": "64000"})


def _position(amt):
    return _ok([{"symbol": "BTCUSDT", "positionAmt": str(amt), "entryPrice": "64000"}])


def _balance():
    return _ok([{"asset": "USDT", "balance": "1000"}])


def test_no_submission_short_circuits():
    result = reconcile_signed_testnet(
        _order_result(submitted=False), _MockAdapter(_filled_order(), _position(0), _balance())
    )
    assert result["status"] == "NO_SUBMISSION"


def test_reconciled_when_fill_matches_position():
    adapter = _MockAdapter(_filled_order("0.001"), _position(0.001), _balance())
    result = reconcile_signed_testnet(_order_result(), adapter)
    assert result["status"] == "RECONCILED", result
    assert result["mismatches"] == []
    assert result["actual"]["position_amt"] == 0.001


def test_mismatch_filled_but_no_position():
    adapter = _MockAdapter(_filled_order("0.001"), _position(0), _balance())
    result = reconcile_signed_testnet(_order_result(), adapter)
    assert result["status"] == "MISMATCH"
    assert "order_filled_but_no_open_position" in result["mismatches"]


def test_mismatch_buy_order_but_short_position():
    adapter = _MockAdapter(_filled_order("0.001"), _position(-0.001), _balance())
    result = reconcile_signed_testnet(_order_result(side="BUY"), adapter)
    assert result["status"] == "MISMATCH"
    assert "buy_order_but_short_position" in result["mismatches"]


def test_mismatch_filled_qty_vs_position_size():
    adapter = _MockAdapter(_filled_order("0.001"), _position(0.005), _balance())
    result = reconcile_signed_testnet(_order_result(), adapter)
    assert result["status"] == "MISMATCH"
    assert "filled_qty_does_not_match_position_size" in result["mismatches"]


def test_unreconciled_when_query_fails():
    adapter = _MockAdapter({"ok": False, "http_status": 500}, _position(0.001), _balance())
    result = reconcile_signed_testnet(_order_result(), adapter)
    assert result["status"] == "UNRECONCILED"
    assert "order_status_query_failed" in result["unreachable"]


def test_reconciliation_never_exposes_secret_fields():
    adapter = _MockAdapter(_filled_order(), _position(0.001), _balance())
    result = reconcile_signed_testnet(_order_result(), adapter)
    text = repr(result).lower()
    assert "signature" not in text and "secret" not in text
