from __future__ import annotations

from typing import Any

from core.json_io import read_storage_json, write_storage_json
from core.time_utils import utc_now_iso

REQUIRED_OUTPUTS = [
    "coinalyze_market_data.json",
    "market_snapshot.json",
    "market_context.json",
    "dynamic_setup_result.json",
    "research_cycle_result.json",
    "research_decision_result.json",
    "trading_cycle_result.json",
    "telegram_alert_result.json",
    "operational_dry_run_result.json",
]


def check_scheduler_health() -> dict[str, Any]:
    checks = []
    failures = 0
    warnings = 0

    for filename in REQUIRED_OUTPUTS:
        data = read_storage_json(filename, default=None)
        ok = data is not None
        checks.append({"file": filename, "status": "OK" if ok else "MISSING"})
        if not ok:
            failures += 1

    trading = read_storage_json("trading_cycle_result.json", default={})
    if trading and trading.get("mode") != "paper":
        warnings += 1
        checks.append({"file": "trading_cycle_result.json", "status": "WARNING", "message": "mode is not paper"})

    status = "HEALTHY" if failures == 0 else "UNHEALTHY"
    result = {
        "schema_version": "step80.scheduler_health.v1",
        "generated_at": utc_now_iso(),
        "status": status,
        "error_failures": failures,
        "warning_failures": warnings,
        "checks": checks,
    }
    write_storage_json("scheduler_health_result.json", result)
    return result
