from __future__ import annotations

from config.settings import Settings, ensure_storage_dirs, storage_path
from core.json_io import write_json
from core.time_utils import utc_now_iso


def run_runtime_guard() -> dict:
    ensure_storage_dirs()
    checks = [
        {"name": "TRADING_MODE_PAPER", "passed": Settings.TRADING_MODE == "paper", "value": Settings.TRADING_MODE},
        {"name": "DRY_RUN_ENABLED", "passed": Settings.DRY_RUN is True, "value": Settings.DRY_RUN},
        {"name": "STORAGE_DIR_AVAILABLE", "passed": Settings.STORAGE_DIR.exists(), "value": str(Settings.STORAGE_DIR)},
    ]
    allowed = all(item["passed"] for item in checks)
    result = {
        "status": "PASSED" if allowed else "FAILED",
        "allowed": allowed,
        "checks": checks,
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("runtime_guard_result.json"), result)
    return result
