from __future__ import annotations

from pathlib import Path

from config.settings import STORAGE_DIR
from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso


PAPER_WATCH_MODE = "PAPER_REPORT_ONLY"
ORDER_EXECUTION_ENABLED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False


def storage_path(relative_path: str | Path) -> Path:
    """Backward-compatible storage path helper for legacy v1 paper-watch outputs."""
    path = Path(relative_path)
    return path if path.is_absolute() else Path(STORAGE_DIR) / path


def write_json(path: str | Path, data: dict) -> None:
    atomic_write_json(path, data)


def finalize_paper_watch(signal: dict, current_price: float | int | None) -> dict:
    result = {
        "name": "PAPER_WATCH_MANAGER",
        "status": "PAPER_WATCH_FINALIZED",
        "mode": "paper",
        "paper_watch_mode": PAPER_WATCH_MODE,
        "signal": signal,
        "current_price": current_price,
        "position_opened": False,
        "reason": "Dry-run/paper-watch mode only.",
        "order_execution_enabled_by_this_module": ORDER_EXECUTION_ENABLED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("paper_watch_result.json"), result)
    write_json(storage_path("reports/paper_performance_report.json"), result)
    return result
