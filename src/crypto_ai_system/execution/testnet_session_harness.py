"""Phase 10: repeated signed-testnet sessions with aggregate stats.

A *session* is one open (BUY) followed by one close (SELL reduceOnly). The
harness runs N sessions, each order going through the same guarded path as a
single order (``execute_order_intent`` -> final guard -> adapter) and each leg
reconciled against the exchange. It collects fill rate, slippage, latency, and
balance change so testnet stability can be measured before live.

Every collaborator is injectable so the harness is unit-testable without a
network or real keys. The runner (``run_testnet_session.py``) wires the real
guarded functions.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from core.time_utils import utc_now_iso

from crypto_ai_system.execution.idempotency import enrich_order_identity

# submit_fn(intent) -> order_result ; reconcile_fn() -> reconciliation
SubmitFn = Callable[[dict], dict]
ReconcileFn = Callable[[], dict]
PriceFn = Callable[[], float]
BalanceFn = Callable[[], float]

_SUBMITTED_STATUS = "SIGNED_TESTNET_ORDER_SUBMITTED"
_BLOCKED_PREFIX = "SIGNED_TESTNET_"  # BLOCKED / REPAIR_REQUIRED statuses


def _size(notional: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return max(0.001, round(notional / price, 3))


def build_market_intent(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    *,
    reduce_only: bool,
    gate_id: str,
) -> dict:
    intent = {
        "created_at": utc_now_iso(),
        "status": "ORDER_INTENT_CREATED",
        "execution_stage": "signed_testnet",
        "decision_stage": "signed_testnet",
        "symbol": symbol,
        "direction": "LONG" if side == "BUY" else "SHORT",
        "side": side,
        "order_type": "MARKET_SIGNED_TESTNET",
        "order_type_exchange": "MARKET",
        "entry_price": price,
        "quantity": quantity,
        "order_notional_usdt": round(quantity * price, 2),
        "notional_usdt": round(quantity * price, 2),
        "reduce_only": reduce_only,
        # Connectivity harness: verifies venue plumbing, not the strategy. The
        # RiskGate approval is synthetic and marked, so these orders are never
        # aggregated as strategy performance.
        "connectivity_test": True,
        "pre_order_risk_gate_approved": True,
        "risk_gate_id": gate_id,
        "order_intent_created": True,
    }
    return enrich_order_identity(intent)


def _leg_metrics(order_result: dict, reconciliation: dict, expected_price: float,
                 side: str, latency_ms: float) -> dict:
    actual = (reconciliation or {}).get("actual") or {}
    avg_fill = actual.get("avg_fill_price")
    slippage_bps = None
    if avg_fill and expected_price:
        # Positive = worse for the taker (paid more on BUY, received less on SELL).
        raw = (float(avg_fill) - expected_price) / expected_price * 10000.0
        slippage_bps = round(raw if side == "BUY" else -raw, 3)
    return {
        "submitted": bool(order_result.get("external_order_submission_performed")),
        "order_status": order_result.get("status"),
        "exchange_order_id": order_result.get("exchange_order_id"),
        "reconcile_status": (reconciliation or {}).get("status"),
        # Surface WHY a leg failed to reconcile (e.g. a residual position makes the
        # filled qty not match the position size) so the report is self-diagnosing.
        "mismatches": (reconciliation or {}).get("mismatches"),
        "position_amt": actual.get("position_amt"),
        "expected_price": expected_price,
        "avg_fill_price": avg_fill,
        "slippage_bps": slippage_bps,
        "latency_ms": round(latency_ms, 1),
        "wallet_balance_usdt": actual.get("wallet_balance_usdt"),
    }


def run_one_session(
    symbol: str,
    notional: float,
    price_fn: PriceFn,
    *,
    submit_fn: SubmitFn,
    reconcile_fn: ReconcileFn,
    session_id: str,
) -> dict:
    open_price = price_fn()
    quantity = _size(notional, open_price)

    open_intent = build_market_intent(
        symbol, "BUY", quantity, open_price, reduce_only=False, gate_id=f"{session_id}_open"
    )
    t0 = time.perf_counter()
    open_result = submit_fn(open_intent)
    open_latency = (time.perf_counter() - t0) * 1000.0
    open_recon = reconcile_fn()
    open_leg = _leg_metrics(open_result, open_recon, open_price, "BUY", open_latency)

    close_leg: dict | None = None
    if open_leg["submitted"]:
        close_price = price_fn()
        close_intent = build_market_intent(
            symbol, "SELL", quantity, close_price, reduce_only=True,
            gate_id=f"{session_id}_close",
        )
        t1 = time.perf_counter()
        close_result = submit_fn(close_intent)
        close_latency = (time.perf_counter() - t1) * 1000.0
        close_recon = reconcile_fn()
        close_leg = _leg_metrics(close_result, close_recon, close_price, "SELL", close_latency)

    legs_ok = open_leg["reconcile_status"] == "RECONCILED" and (
        close_leg is not None and close_leg["reconcile_status"] == "RECONCILED"
    )
    if not open_leg["submitted"]:
        status = "BLOCKED"
    elif legs_ok:
        status = "OK"
    else:
        status = "PARTIAL"

    return {
        "session_id": session_id,
        "symbol": symbol,
        "quantity": quantity,
        "status": status,
        "open": open_leg,
        "close": close_leg,
    }


def aggregate(records: list[dict], start_balance: float | None,
              end_balance: float | None) -> dict:
    legs: list[dict] = []
    for rec in records:
        legs.append(rec["open"])
        if rec.get("close"):
            legs.append(rec["close"])

    submitted = [leg for leg in legs if leg["submitted"]]
    filled = [leg for leg in legs if leg["order_status"] == _SUBMITTED_STATUS]
    reconciled = [leg for leg in legs if leg["reconcile_status"] == "RECONCILED"]
    slippages = [leg["slippage_bps"] for leg in legs if leg["slippage_bps"] is not None]
    latencies = [leg["latency_ms"] for leg in submitted if leg["latency_ms"] is not None]

    def _avg(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    total_cost = None
    if start_balance is not None and end_balance is not None:
        total_cost = round(start_balance - end_balance, 8)

    return {
        "sessions_run": len(records),
        "sessions_ok": sum(1 for r in records if r["status"] == "OK"),
        "orders_submitted": len(submitted),
        "orders_reconciled": len(reconciled),
        "reconcile_rate": round(len(reconciled) / len(submitted), 4) if submitted else None,
        "avg_slippage_bps": _avg(slippages),
        "avg_latency_ms": _avg(latencies),
        "start_balance_usdt": start_balance,
        "end_balance_usdt": end_balance,
        "total_round_trip_cost_usdt": total_cost,
    }


def run_sessions(
    n: int,
    symbol: str,
    notional: float,
    price_fn: PriceFn,
    *,
    submit_fn: SubmitFn,
    reconcile_fn: ReconcileFn,
    balance_fn: BalanceFn | None = None,
) -> dict:
    start_balance = balance_fn() if balance_fn else None
    records: list[dict] = []
    for i in range(n):
        record = run_one_session(
            symbol, notional, price_fn,
            submit_fn=submit_fn, reconcile_fn=reconcile_fn,
            session_id=f"session_{i + 1}",
        )
        records.append(record)
        # Stop early when the guard blocks (e.g. daily cap reached).
        if record["status"] == "BLOCKED":
            break
    end_balance = balance_fn() if balance_fn else None

    return {
        "created_at": utc_now_iso(),
        "requested_sessions": n,
        "sessions": records,
        "aggregate": aggregate(records, start_balance, end_balance),
    }
