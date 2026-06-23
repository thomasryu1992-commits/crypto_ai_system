from __future__ import annotations

from config.settings import storage_path
from core.json_io import write_json
from core.time_utils import utc_now_iso


def finalize_paper_watch(signal: dict, current_price: float | int | None) -> dict:
    result = {
        "name": "PAPER_WATCH_MANAGER",
        "status": "PAPER_WATCH_FINALIZED",
        "mode": "paper",
        "signal": signal,
        "current_price": current_price,
        "position_opened": False,
        "reason": "Dry-run/paper-watch mode only.",
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("paper_watch_result.json"), result)
    write_json(storage_path("reports/paper_performance_report.json"), result)
    return result
