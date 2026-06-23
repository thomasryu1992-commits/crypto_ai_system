from __future__ import annotations

from config.settings import ORDER_RESULT_PATH, PAPER_STATE_PATH, RECONCILIATION_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


def run_reconciler() -> dict:
    order = read_json(ORDER_RESULT_PATH, {})
    paper = read_json(PAPER_STATE_PATH, {})
    result = {
        "created_at": utc_now_iso(),
        "status": "RECONCILED",
        "order_status": order.get("status"),
        "paper_active": bool(paper.get("active_position")),
        "notes": [],
    }
    if order.get("status") == "SHADOW_ONLY" and not paper.get("active_position"):
        result["notes"].append("shadow_order_exists_without_active_paper_position")
    atomic_write_json(RECONCILIATION_PATH, result)
    log_event("reconciliation_completed", {"status": result["status"], "notes": result["notes"]})
    return result


def main() -> None:
    result = run_reconciler()
    print(f"Reconciler: {result['status']}")


if __name__ == "__main__":
    main()
