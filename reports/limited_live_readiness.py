from __future__ import annotations

from config.settings import (
    LIMITED_LIVE_READINESS_REPORT_PATH,
    MAX_LIVE_POSITION_USDT,
    MAX_ORDER_NOTIONAL_USDT,
)
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from config.settings import (
    DATA_HEALTH_PATH,
    LIVE_READINESS_PATH,
    RISK_STATUS_PATH,
    SPREADSHEET_SYNC_RESULT_PATH,
    STEP150_VALIDATION_PATH,
)


def build_limited_live_readiness_report() -> dict:
    data_health = read_json(DATA_HEALTH_PATH, {})
    risk = read_json(RISK_STATUS_PATH, {})
    live = read_json(LIVE_READINESS_PATH, {})
    spreadsheet = read_json(SPREADSHEET_SYNC_RESULT_PATH, {})
    validation = read_json(STEP150_VALIDATION_PATH, {})

    checks = {
        "data_health_healthy": data_health.get("status") == "HEALTHY",
        "risk_normal": risk.get("status") == "NORMAL",
        "spreadsheet_sync_available": spreadsheet.get("status") in {"EXPORTED_LOCAL_BACKUP", "QUEUED_FOR_GOOGLE_SHEETS_RETRY"},
        "step150_validation_passed": validation.get("status") == "PASSED",
        "live_readiness_currently_blocked": live.get("ready") is False,
    }
    failed = [k for k, v in checks.items() if not v]
    passed = [k for k, v in checks.items() if v]
    status = "NOT_READY_FOR_LIMITED_LIVE"
    if not failed:
        status = "READY_FOR_TESTNET_ONLY"

    report = {
        "created_at": utc_now_iso(),
        "readiness_status": status,
        "checks": checks,
        "checks_passed": passed,
        "checks_failed": failed,
        "max_live_position_usdt": MAX_LIVE_POSITION_USDT,
        "max_order_notional_usdt": MAX_ORDER_NOTIONAL_USDT,
        "required_next_steps": [
            "Connect real market data",
            "Run at least 7 wall-clock days of paper forward test",
            "Implement Binance testnet signed order flow",
            "Run at least 2 weeks of testnet execution",
            "Manually review live unlock checklist",
        ],
    }
    atomic_write_json(LIMITED_LIVE_READINESS_REPORT_PATH, report)
    return report


def main() -> None:
    report = build_limited_live_readiness_report()
    print(f"Limited live readiness: {report['readiness_status']}")


if __name__ == "__main__":
    main()
