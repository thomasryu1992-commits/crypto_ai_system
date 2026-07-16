"""Live-canary submit + reconcile glue (standalone boundary).

Deliberately NOT wired into ``execution_port.select_adapter`` / the pipeline: the
pipeline still refuses live, and the canary is reachable only from its dedicated
operator runner. This module runs the final guard, and only if it returns READY
does it construct the live adapter and submit exactly one order. Reconciliation
reuses the adapter-agnostic ``reconcile_signed_testnet`` comparison against the
live venue.
"""

from __future__ import annotations

from typing import Any

import config.settings as settings
from config.settings import ORDER_RESULT_PATH, RECONCILIATION_PATH
from core.event_log import log_event
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso

from crypto_ai_system.execution.live_canary_adapter import LiveCanaryAdapter
from crypto_ai_system.execution.live_canary_final_guard import (
    evaluate_live_canary_final_guard,
    record_submission,
)
from crypto_ai_system.execution.signed_testnet_reconciliation import reconcile_signed_testnet


def submit_live_canary_order(intent: dict[str, Any]) -> dict[str, Any]:
    """Guard, then submit exactly one live canary order. Fails closed.

    Nothing is signed or sent unless the final guard returns READY. The result is
    persisted to ORDER_RESULT_PATH for reconciliation, and a real submission is
    marked ``external_order_submission_performed`` and counted.
    """
    guard = evaluate_live_canary_final_guard(intent)
    result: dict[str, Any] = {
        "created_at": utc_now_iso(),
        "mode": "LIVE_CANARY",
        "intent": intent,
        "final_guard": guard,
        "connectivity_test": bool(intent.get("connectivity_test")),
        "exchange_order_id": None,
        "filled": False,
        "external_order_submission_performed": False,
    }

    if not guard.get("approved"):
        result["state"] = "REJECTED"
        result["status"] = f"LIVE_CANARY_{guard.get('status', 'BLOCKED')}"
        result["mode"] = "LIVE_CANARY_GUARD_BLOCK"
        atomic_write_json(ORDER_RESULT_PATH, result)
        log_event("live_canary_order_blocked", {"status": result["status"], "blocks": guard.get("blocks")})
        return result

    adapter = LiveCanaryAdapter(
        api_key=settings.LIVE_CANARY_API_KEY,
        api_secret=settings.LIVE_CANARY_API_SECRET,
        base_url=settings.LIVE_CANARY_BASE_URL,
    )
    submit = adapter.submit_order(intent)
    submitted = bool(submit.get("submitted"))
    if submitted:
        record_submission()

    result["mode"] = "LIVE_CANARY_ADAPTER"
    result["state"] = "SUBMITTED" if submitted else "UNKNOWN"
    result["status"] = "LIVE_CANARY_ORDER_SUBMITTED" if submitted else "LIVE_CANARY_SUBMIT_FAILED"
    result["submit_result"] = submit
    result["exchange_order_id"] = submit.get("exchange_order_id")
    result["client_order_id"] = submit.get("client_order_id")
    result["external_order_submission_performed"] = submitted
    atomic_write_json(ORDER_RESULT_PATH, result)
    log_event(
        "live_canary_order_attempted",
        {"status": result["status"], "state": result["state"], "client_order_id": submit.get("client_order_id")},
    )
    return result


def run_live_canary_reconciliation() -> dict[str, Any]:
    """Reconcile the latest live-canary order result against the live exchange."""
    order_result = read_json(ORDER_RESULT_PATH, {})

    if not order_result.get("external_order_submission_performed"):
        result = {
            "created_at": utc_now_iso(),
            "status": "NO_SUBMISSION",
            "mode": "LIVE_CANARY_RECONCILIATION",
            "mismatches": [],
            "notes": ["no external live submission to reconcile"],
        }
        atomic_write_json(RECONCILIATION_PATH, result)
        log_event("live_canary_reconciliation", {"status": result["status"]})
        return result

    try:
        adapter = LiveCanaryAdapter(
            api_key=settings.LIVE_CANARY_API_KEY,
            api_secret=settings.LIVE_CANARY_API_SECRET,
            base_url=settings.LIVE_CANARY_BASE_URL,
        )
        result = reconcile_signed_testnet(order_result, adapter)
        result["mode"] = "LIVE_CANARY_RECONCILIATION"
    except Exception as exc:  # noqa: BLE001 - fail closed to UNRECONCILED
        result = {
            "created_at": utc_now_iso(),
            "status": "UNRECONCILED",
            "mode": "LIVE_CANARY_RECONCILIATION",
            "mismatches": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    atomic_write_json(RECONCILIATION_PATH, result)
    log_event(
        "live_canary_reconciliation",
        {"status": result.get("status"), "mismatches": result.get("mismatches", [])},
    )
    return result
