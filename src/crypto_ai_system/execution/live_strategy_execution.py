"""L3: live-strategy submit + reconcile glue.

The execution-side counterpart of the live-strategy final guard: runs the guard,
and only if it returns READY constructs the mainnet adapter (the same hardened
``LiveCanaryAdapter`` class — host allowlist, HMAC, redaction, no auto-retry) with
the SEPARATE live-strategy key and submits exactly one order. Reconciliation
reuses the adapter-agnostic ``reconcile_signed_testnet`` comparison against the
live venue.

Unlike the canary this path is reachable from the pipeline (via the ``live``
execution stage), but every layer above it — stage routing, the PreOrderRiskGate
record, and this guard — must independently approve before anything is signed.
"""

from __future__ import annotations

from typing import Any

import config.settings as settings
from config.settings import ORDER_RESULT_PATH, RECONCILIATION_PATH
from core.event_log import log_event
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso

from crypto_ai_system.execution.live_canary_adapter import LiveCanaryAdapter
from crypto_ai_system.execution.live_order_final_guard import (
    evaluate_live_close_guard,
    evaluate_live_order_final_guard,
    record_submission,
)
from crypto_ai_system.execution.retry_policy import is_ambiguous_submit, resolve_ambiguous_submit
from crypto_ai_system.execution.signed_testnet_reconciliation import reconcile_signed_testnet


def _resolve_submit(adapter: LiveCanaryAdapter, intent: dict[str, Any], submit: dict[str, Any]) -> tuple[bool, bool, dict | None]:
    """(submitted, unresolved, resolution) for a submit result.

    An ambiguous failure (timeout / 5xx / rate-limit after the POST left this
    process) is resolved by querying the client order id. ``unresolved`` means
    even the query failed: the order may be live on the venue, so the caller
    must account for it (daily budget + reconciliation), never assume it away.
    """
    submitted = bool(submit.get("submitted"))
    if submitted or not is_ambiguous_submit(submit):
        return submitted, False, None
    resolution = resolve_ambiguous_submit(
        adapter.query_order, str(intent.get("symbol")), str(intent.get("client_order_id"))
    )
    if resolution.get("order_exists") is True:
        return True, False, resolution
    if resolution.get("order_exists") is False:
        return False, False, resolution
    return False, True, resolution


def _strategy_adapter() -> LiveCanaryAdapter:
    return LiveCanaryAdapter(
        api_key=settings.LIVE_STRATEGY_API_KEY,
        api_secret=settings.LIVE_STRATEGY_API_SECRET,
        base_url=settings.LIVE_STRATEGY_BASE_URL,
    )


def submit_live_strategy_order(
    intent: dict[str, Any], *, current_open_notional_usdt: float = 0.0
) -> dict[str, Any]:
    """Guard, then submit exactly one live strategy order. Fails closed.

    Nothing is signed or sent unless the final guard returns READY (which itself
    requires a verified stage='live' RiskGate record, the daily-loss breaker
    clear, promotion evidence, and every cap satisfied).
    """
    guard = evaluate_live_order_final_guard(
        intent, current_open_notional_usdt=current_open_notional_usdt
    )
    result: dict[str, Any] = {
        "created_at": utc_now_iso(),
        "mode": "LIVE_STRATEGY",
        "intent": intent,
        "final_guard": guard,
        "exchange_order_id": None,
        "filled": False,
        "external_order_submission_performed": False,
    }

    if not guard.get("approved"):
        result["state"] = "REJECTED"
        result["status"] = f"LIVE_STRATEGY_{guard.get('status', 'BLOCKED')}"
        result["mode"] = "LIVE_STRATEGY_GUARD_BLOCK"
        log_event("live_strategy_order_blocked", {"status": result["status"], "blocks": guard.get("blocks")})
        return result

    adapter = _strategy_adapter()
    submit = adapter.submit_order(intent)
    submitted, unresolved, resolution = _resolve_submit(adapter, intent, submit)
    # An unresolved-ambiguous submit may be live on the venue: it consumes the
    # daily budget and is handed to reconciliation exactly like a confirmed one
    # (the position kernel only opens on a RECONCILED fill, so nothing is
    # fabricated if it turns out the order never existed).
    if submitted or unresolved:
        record_submission()

    result["mode"] = "LIVE_STRATEGY_ADAPTER"
    result["state"] = "SUBMITTED" if submitted else "UNKNOWN"
    if submitted:
        result["status"] = "LIVE_STRATEGY_ORDER_SUBMITTED"
    elif unresolved:
        result["status"] = "LIVE_STRATEGY_SUBMIT_UNRESOLVED"
    else:
        result["status"] = "LIVE_STRATEGY_SUBMIT_FAILED"
    result["submit_result"] = submit
    if resolution is not None:
        result["ambiguous_submit_resolution"] = resolution
        result["submit_confirmed_by_query"] = submitted
    result["exchange_order_id"] = submit.get("exchange_order_id")
    result["client_order_id"] = submit.get("client_order_id")
    result["external_order_submission_performed"] = submitted or unresolved
    log_event(
        "live_strategy_order_attempted",
        {"status": result["status"], "state": result["state"], "client_order_id": submit.get("client_order_id")},
        severity="WARNING" if unresolved else "INFO",
    )
    return result


def submit_live_close_order(intent: dict[str, Any]) -> dict[str, Any]:
    """Submit a reduceOnly CLOSE of the open live position (narrow close guard).

    Risk-reducing: exempt from the loss breaker / kill switch / caps (see
    ``evaluate_live_close_guard``), and does NOT consume the daily entry-order
    budget — a tripped daily cap must never trap an open position.
    """
    guard = evaluate_live_close_guard(intent)
    result: dict[str, Any] = {
        "created_at": utc_now_iso(),
        "mode": "LIVE_STRATEGY_CLOSE",
        "intent": intent,
        "final_guard": guard,
        "exchange_order_id": None,
        "filled": False,
        "external_order_submission_performed": False,
    }
    if not guard.get("approved"):
        result["state"] = "REJECTED"
        result["status"] = f"LIVE_CLOSE_{guard.get('status', 'BLOCKED')}"
        result["mode"] = "LIVE_CLOSE_GUARD_BLOCK"
        log_event("live_close_order_blocked", {"status": result["status"], "blocks": guard.get("blocks")}, severity="WARNING")
        return result

    adapter = _strategy_adapter()
    submit = adapter.submit_order(intent)
    submitted, unresolved, resolution = _resolve_submit(adapter, intent, submit)

    result["mode"] = "LIVE_STRATEGY_CLOSE_ADAPTER"
    result["state"] = "SUBMITTED" if submitted else "UNKNOWN"
    if submitted:
        result["status"] = "LIVE_CLOSE_ORDER_SUBMITTED"
    elif unresolved:
        result["status"] = "LIVE_CLOSE_SUBMIT_UNRESOLVED"
    else:
        result["status"] = "LIVE_CLOSE_SUBMIT_FAILED"
    result["submit_result"] = submit
    if resolution is not None:
        result["ambiguous_submit_resolution"] = resolution
        result["submit_confirmed_by_query"] = submitted
    result["exchange_order_id"] = submit.get("exchange_order_id")
    result["client_order_id"] = submit.get("client_order_id")
    # An unresolved close may be live at the venue: report it as performed so the
    # kernel keeps the SAME client order id pending instead of racing a second
    # reduceOnly close against a fill it cannot see yet.
    result["external_order_submission_performed"] = submitted or unresolved
    log_event(
        "live_close_order_attempted",
        {"status": result["status"], "client_order_id": submit.get("client_order_id")},
        severity="INFO" if submitted else "WARNING",
    )
    return result


def query_live_order(symbol: str, client_order_id: str) -> dict[str, Any]:
    """Signed GET of one live order's state (used to read the close fill)."""
    return _strategy_adapter().query_order(symbol, client_order_id)


def run_live_strategy_reconciliation() -> dict[str, Any]:
    """Reconcile the latest live-strategy order result against the live exchange."""
    order_result = read_json(ORDER_RESULT_PATH, {})

    if not order_result.get("external_order_submission_performed"):
        result = {
            "created_at": utc_now_iso(),
            "status": "NO_SUBMISSION",
            "mode": "LIVE_STRATEGY_RECONCILIATION",
            "mismatches": [],
            "notes": ["no external live submission to reconcile"],
        }
        atomic_write_json(RECONCILIATION_PATH, result)
        log_event("live_strategy_reconciliation", {"status": result["status"]})
        return result

    try:
        result = reconcile_signed_testnet(order_result, _strategy_adapter())
        result["mode"] = "LIVE_STRATEGY_RECONCILIATION"
    except Exception as exc:  # noqa: BLE001 - fail closed to UNRECONCILED
        result = {
            "created_at": utc_now_iso(),
            "status": "UNRECONCILED",
            "mode": "LIVE_STRATEGY_RECONCILIATION",
            "mismatches": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    atomic_write_json(RECONCILIATION_PATH, result)
    log_event(
        "live_strategy_reconciliation",
        {"status": result.get("status"), "mismatches": result.get("mismatches", [])},
    )
    return result
