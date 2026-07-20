from __future__ import annotations

from pathlib import Path

from config.settings import ORDER_RESULT_PATH, PAPER_STATE_PATH, RECONCILIATION_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


RECONCILER_MODE = "CHECK_ONLY"
LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE = False
EXTERNAL_EXECUTION_SYNC_PERFORMED = False


def run_reconciler() -> dict:
    # Step295: if a Step294 paper execution record exists, reconcile the full
    # paper-only execution evidence instead of using the legacy shadow check.
    # This path performs no live position sync and no external execution sync.
    try:
        from crypto_ai_system.config import load_config
        from crypto_ai_system.execution.paper_reconciliation_v2 import reconcile_latest_paper_execution

        cfg = load_config(".")
        latest_dir = cfg.get("storage.latest_dir", "storage/latest")
        latest = Path(latest_dir)
        if not latest.is_absolute():
            latest = cfg.root / latest
        paper_record_path = latest / "paper_execution_record.json"
        if paper_record_path.exists():
            result = reconcile_latest_paper_execution(cfg=cfg)
            atomic_write_json(RECONCILIATION_PATH, result)
            log_event("reconciliation_completed", {"status": result.get("status"), "step295": True})
            return result
    except Exception as exc:
        # Legacy reconciler remains the safe compatibility fallback. Do not open
        # live sync or external execution when the Step295 evidence path is invalid.
        fallback_note = f"step295_reconciliation_v2_unavailable:{type(exc).__name__}"
    else:
        fallback_note = "step295_no_paper_execution_record"

    order = read_json(ORDER_RESULT_PATH, {})
    paper = read_json(PAPER_STATE_PATH, {})
    # The legacy fallback compares nothing against a venue, so it must never
    # stamp RECONCILED on an order that actually reached an exchange — those
    # are reconciled by the signed-testnet/live reconcilers. Unreachable from
    # the pipeline today (the trading agent routes external submissions to the
    # venue reconcilers), but defense-in-depth for any direct caller.
    notes = [fallback_note]
    if order.get("external_order_submission_performed"):
        status = "UNRECONCILED"
        notes.append("legacy_fallback_cannot_reconcile_external_submission")
    else:
        status = "RECONCILED"
    result = {
        "created_at": utc_now_iso(),
        "status": status,
        "order_status": order.get("status"),
        "paper_active": bool(paper.get("active_position")),
        "notes": notes,
        "reconciler_mode": RECONCILER_MODE,
        "live_position_sync_enabled_by_this_module": LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE,
        "external_execution_sync_performed": EXTERNAL_EXECUTION_SYNC_PERFORMED,
    }
    if order.get("status") == "SHADOW_ONLY" and not paper.get("active_position"):
        result["notes"].append("shadow_order_exists_without_active_paper_position")
    atomic_write_json(RECONCILIATION_PATH, result)
    log_event("reconciliation_completed", {"status": result["status"], "notes": result["notes"]})
    return result


def reconcile_execution_state() -> dict:
    """Compatibility wrapper: live execution is intentionally disabled in Step158."""
    result = {
        "created_at": utc_now_iso(),
        "status": "NO_LIVE_EXECUTION",
        "mode": "SAFE_COMPATIBILITY_RECONCILE",
        "notes": ["live execution remains blocked; use shadow/order logs only"],
        "reconciler_mode": RECONCILER_MODE,
        "live_position_sync_enabled_by_this_module": LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE,
        "external_execution_sync_performed": EXTERNAL_EXECUTION_SYNC_PERFORMED,
    }
    atomic_write_json(RECONCILIATION_PATH, result)
    log_event("reconciliation_completed", {"status": result["status"]})
    return result


def main() -> None:
    result = run_reconciler()
    print(f"Reconciler: {result['status']}")


if __name__ == "__main__":
    main()
