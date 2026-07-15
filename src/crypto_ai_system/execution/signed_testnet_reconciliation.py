"""Signed-testnet reconciliation: exchange truth vs order intent.

After a signed testnet order is submitted, query the exchange for the order
status (fill), the position, and the balance, and compare against what the
order intent expected. Produces a reconciliation report with an explicit
``status`` (``RECONCILED`` / ``MISMATCH`` / ``UNRECONCILED`` / ``NO_SUBMISSION``)
and a list of mismatches.

Read-only: this only issues signed GET requests; it never places or cancels.
"""

from __future__ import annotations

from typing import Any

import config.settings as settings
from config.settings import ORDER_RESULT_PATH, RECONCILIATION_PATH
from core.event_log import log_event
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso

from crypto_ai_system.execution.signed_testnet_adapter import SignedTestnetAdapter

# Quantity tolerance when comparing filled qty to the resulting position size.
_QTY_TOLERANCE = 1e-8

_FILLED_STATES = {"FILLED", "PARTIALLY_FILLED"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _find(items: Any, key: str, value: str) -> dict | None:
    for item in items or []:
        if isinstance(item, dict) and item.get(key) == value:
            return item
    return None


def reconcile_signed_testnet(order_result: dict, adapter: SignedTestnetAdapter) -> dict:
    """Compare exchange state with the submitted order intent.

    Pure enough to unit-test: pass an adapter (real or mock).
    """
    intent = order_result.get("intent") or {}
    symbol = intent.get("symbol")
    side = intent.get("side")
    client_order_id = order_result.get("client_order_id") or intent.get("client_order_id")
    expected_qty = _float(intent.get("quantity"))

    base = {
        "created_at": utc_now_iso(),
        "mode": "SIGNED_TESTNET_RECONCILIATION",
        "expected": {
            "symbol": symbol,
            "side": side,
            "quantity": expected_qty,
            "client_order_id": client_order_id,
            "exchange_order_id": order_result.get("exchange_order_id"),
        },
    }

    if not order_result.get("external_order_submission_performed") or not order_result.get("exchange_order_id"):
        base["status"] = "NO_SUBMISSION"
        base["mismatches"] = []
        base["notes"] = ["no external testnet submission to reconcile"]
        return base

    order_q = adapter.query_order(symbol, client_order_id)
    positions_q = adapter.get_positions(symbol)
    balance_q = adapter.get_balance()

    unreachable: list[str] = []
    if not order_q.get("ok"):
        unreachable.append("order_status_query_failed")
    if not positions_q.get("ok"):
        unreachable.append("position_query_failed")
    if not balance_q.get("ok"):
        unreachable.append("balance_query_failed")

    order_resp = order_q.get("response") or {}
    order_status = order_resp.get("status") if isinstance(order_resp, dict) else None
    executed_qty = _float(order_resp.get("executedQty")) if isinstance(order_resp, dict) else 0.0
    avg_price = _float(order_resp.get("avgPrice")) if isinstance(order_resp, dict) else 0.0

    position = _find(positions_q.get("response"), "symbol", symbol) or {}
    position_amt = _float(position.get("positionAmt"))
    position_entry = _float(position.get("entryPrice"))

    balance_asset = _find(balance_q.get("response"), "asset", "USDT") or {}
    wallet_balance = _float(balance_asset.get("balance"))

    actual = {
        "order_status": order_status,
        "executed_qty": executed_qty,
        "avg_fill_price": avg_price,
        "position_amt": position_amt,
        "position_entry_price": position_entry,
        "wallet_balance_usdt": wallet_balance,
    }

    mismatches: list[str] = []
    filled = order_status in _FILLED_STATES

    if isinstance(order_resp, dict) and not order_resp.get("orderId"):
        mismatches.append("exchange_order_not_found_by_client_order_id")

    if filled and abs(position_amt) < _QTY_TOLERANCE:
        mismatches.append("order_filled_but_no_open_position")

    if filled and side == "BUY" and position_amt < 0:
        mismatches.append("buy_order_but_short_position")
    if filled and side == "SELL" and position_amt > 0:
        mismatches.append("sell_order_but_long_position")

    if filled and abs(executed_qty - abs(position_amt)) > max(_QTY_TOLERANCE, expected_qty * 1e-6):
        mismatches.append("filled_qty_does_not_match_position_size")

    if unreachable:
        status = "UNRECONCILED"
    elif mismatches:
        status = "MISMATCH"
    else:
        status = "RECONCILED"

    base["status"] = status
    base["actual"] = actual
    base["mismatches"] = mismatches
    base["unreachable"] = unreachable
    base["filled"] = filled
    return base


def run_signed_testnet_reconciliation() -> dict:
    """Read the latest order result and reconcile it against the testnet exchange."""
    order_result = read_json(ORDER_RESULT_PATH, {})

    if not order_result.get("external_order_submission_performed"):
        result = {
            "created_at": utc_now_iso(),
            "status": "NO_SUBMISSION",
            "mode": "SIGNED_TESTNET_RECONCILIATION",
            "mismatches": [],
            "notes": ["no external testnet submission to reconcile"],
        }
        atomic_write_json(RECONCILIATION_PATH, result)
        log_event("signed_testnet_reconciliation", {"status": result["status"]})
        return result

    try:
        adapter = SignedTestnetAdapter(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            base_url=settings.BINANCE_TESTNET_BASE_URL,
        )
        result = reconcile_signed_testnet(order_result, adapter)
    except Exception as exc:  # noqa: BLE001 - fail closed to UNRECONCILED
        result = {
            "created_at": utc_now_iso(),
            "status": "UNRECONCILED",
            "mode": "SIGNED_TESTNET_RECONCILIATION",
            "mismatches": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    atomic_write_json(RECONCILIATION_PATH, result)
    log_event(
        "signed_testnet_reconciliation",
        {"status": result.get("status"), "mismatches": result.get("mismatches", [])},
    )
    return result
