from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from config.settings import LATEST_DIR, STORAGE_DIR, TELEGRAM_ENABLED
from core.json_io import read_json, write_storage_json
from core.time_utils import utc_now_iso

# Stable profile: checks the unified Step1~157E merged pipeline.
# Legacy files remain in the package, but the scheduler should evaluate the
# stable execution path rather than every historical one-off runner.
STABLE_REQUIRED_OUTPUTS = [
    "step150_validation_result.json",
    "step157e_full_validation_result.json",
    "extended_market_snapshot.json",
    "extended_feature_snapshot.json",
    "research_cycle_result.json",
    "research_decision_result.json",
    "trading_cycle_result.json",
    "operational_dry_run_result.json",
    "spreadsheet_sync_result.json",
]

LEGACY_REQUIRED_OUTPUTS = [
    "coinalyze_market_data.json",
    "market_snapshot.json",
    "market_context.json",
    "dynamic_setup_result.json",
    "research_cycle_result.json",
    "research_decision_result.json",
    "trading_cycle_result.json",
    "operational_dry_run_result.json",
]

TELEGRAM_OUTPUT = "telegram_alert_result.json"

BAD_STATUS_VALUES = {"FAILED", "ERROR", "CRASHED", "EXCEPTION"}


def _profile() -> str:
    return os.getenv("SCHEDULER_HEALTH_PROFILE", "stable").strip().lower()


def _read_runtime_json(filename: str) -> tuple[Any | None, str | None]:
    """Read from storage/latest first, then legacy storage root."""
    for base in (Path(LATEST_DIR), Path(STORAGE_DIR)):
        path = base / filename
        if path.exists() and path.is_file():
            return read_json(path, default=None), str(path)
    return None, None


def _is_failed_payload(data: Any) -> tuple[bool, str | None]:
    if not isinstance(data, dict):
        return False, None
    status = str(data.get("status", "")).upper()
    if status in BAD_STATUS_VALUES:
        return True, f"status={status}"
    ok = data.get("ok")
    if ok is False:
        return True, "ok=false"
    if data.get("error") or data.get("error_type"):
        return True, str(data.get("error") or data.get("error_type"))
    return False, None


def _required_outputs() -> list[str]:
    return LEGACY_REQUIRED_OUTPUTS if _profile() == "legacy" else STABLE_REQUIRED_OUTPUTS


def check_scheduler_health() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures = 0
    warnings = 0
    profile = _profile()

    for filename in _required_outputs():
        data, path = _read_runtime_json(filename)
        if data is None:
            checks.append({"file": filename, "status": "MISSING", "path": path})
            failures += 1
            continue
        failed_payload, reason = _is_failed_payload(data)
        if failed_payload:
            checks.append({"file": filename, "status": "FAILED", "path": path, "reason": reason})
            failures += 1
        else:
            checks.append({"file": filename, "status": "OK", "path": path})

    telegram_data, telegram_path = _read_runtime_json(TELEGRAM_OUTPUT)
    if TELEGRAM_ENABLED:
        telegram_ok = telegram_data is not None and not _is_failed_payload(telegram_data)[0]
        checks.append({
            "file": TELEGRAM_OUTPUT,
            "status": "OK" if telegram_ok else "MISSING_OR_FAILED",
            "path": telegram_path,
            "required_when": "TELEGRAM_ENABLED=true",
        })
        if not telegram_ok:
            failures += 1
    else:
        checks.append({
            "file": TELEGRAM_OUTPUT,
            "status": "OK" if telegram_data is not None else "SKIPPED",
            "path": telegram_path,
            "reason": "Telegram disabled; not counted as error.",
        })

    trading, _ = _read_runtime_json("trading_cycle_result.json")
    if isinstance(trading, dict):
        mode = trading.get("mode") or trading.get("trading_mode")
        if mode and str(mode).lower() not in {"paper", "dry_run", "skipped"}:
            warnings += 1
            checks.append({
                "file": "trading_cycle_result.json",
                "status": "WARNING",
                "message": f"mode is {mode}, expected paper/dry_run/skipped",
            })

    status = "HEALTHY" if failures == 0 else "UNHEALTHY"
    result = {
        "schema_version": "step157e.scheduler_health.stable.v1",
        "generated_at": utc_now_iso(),
        "profile": profile,
        "status": status,
        "error_failures": failures,
        "warning_failures": warnings,
        "checks": checks,
    }
    write_storage_json("scheduler_health_result.json", result)
    return result
