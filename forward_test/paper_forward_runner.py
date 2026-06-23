from __future__ import annotations

from config.settings import FORWARD_TEST_LOG_PATH, FORWARD_TEST_SUMMARY_PATH
from core.json_io import append_jsonl, atomic_write_json
from core.time_utils import utc_now_iso
from run_full_cycle import run_full_cycle


def run_forward_iteration(iteration: int = 1) -> dict:
    result = run_full_cycle()
    paper_status = result.get("trading", {}).get("paper_result", {}).get("status")
    row = {
        "timestamp": utc_now_iso(),
        "iteration": iteration,
        "final_decision": result["trade_decision"]["final_decision"],
        "data_health": result["data_health"]["status"],
        "risk": result["risk"]["status"],
        "order_status": result["order"]["status"],
        "paper_position_status": paper_status,
        "spreadsheet_status": result["spreadsheet"]["status"],
    }
    append_jsonl(FORWARD_TEST_LOG_PATH, row)
    return row


def summarize_forward_test(iterations: int, rows: list[dict]) -> dict:
    decisions = {}
    for row in rows:
        decisions[row["final_decision"]] = decisions.get(row["final_decision"], 0) + 1
    summary = {
        "created_at": utc_now_iso(),
        "requested_iterations": iterations,
        "completed_iterations": len(rows),
        "decision_counts": decisions,
        "status": "COMPLETED",
        "notes": [
            "This runner simulates scheduled forward cycles.",
            "Use Windows Task Scheduler, cron, GitHub Actions, or cloud scheduler for real wall-clock operation.",
        ],
    }
    atomic_write_json(FORWARD_TEST_SUMMARY_PATH, summary)
    return summary


def run_forward_test(iterations: int = 7) -> dict:
    rows = []
    for i in range(1, iterations + 1):
        rows.append(run_forward_iteration(i))
    return summarize_forward_test(iterations, rows)
