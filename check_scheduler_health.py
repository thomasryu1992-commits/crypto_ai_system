from __future__ import annotations

from config.settings import (
    DATA_HEALTH_PATH,
    RISK_STATUS_PATH,
    SCHEDULER_HEALTH_PATH,
    SPREADSHEET_SYNC_RESULT_PATH,
    TRADE_DECISION_PATH,
)
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso


def check_scheduler_health() -> dict:
    required = {
        "data_health": DATA_HEALTH_PATH,
        "risk_status": RISK_STATUS_PATH,
        "trade_decision": TRADE_DECISION_PATH,
        "spreadsheet_sync": SPREADSHEET_SYNC_RESULT_PATH,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    data_health = read_json(DATA_HEALTH_PATH, {})
    status = "HEALTHY" if not missing else "UNHEALTHY"
    result = {
        "created_at": utc_now_iso(),
        "status": status,
        "missing_outputs": missing,
        "data_health_status": data_health.get("status"),
        "allow_trading": data_health.get("allow_trading"),
    }
    atomic_write_json(SCHEDULER_HEALTH_PATH, result)
    return result


def main() -> None:
    result = check_scheduler_health()
    print(f"Scheduler Health: {result['status']}")


if __name__ == "__main__":
    main()
