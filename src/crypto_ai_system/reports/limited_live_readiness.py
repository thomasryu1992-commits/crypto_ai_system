from __future__ import annotations

from typing import Any

from config.settings import (
    DATA_HEALTH_PATH,
    LIMITED_LIVE_READINESS_REPORT_PATH,
    LIVE_READINESS_PATH,
    MAX_LIVE_POSITION_USDT,
    MAX_ORDER_NOTIONAL_USDT,
    RISK_STATUS_PATH,
    SPREADSHEET_SYNC_RESULT_PATH,
    STEP150_VALIDATION_PATH,
)
from core.event_log import log_event
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from crypto_ai_system.execution.live_guard import run_live_readiness_check

LIMITED_LIVE_READINESS_VERSION = "step266_operational_flow_repair_limited_live_readiness"
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
REAL_TELEGRAM_SEND_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False

_REQUIRED_NEXT_STEPS = [
    "Connect real market data and validate stored Feature Store matrices",
    "Run at least 7 wall-clock days of paper forward test",
    "Validate exchange adapter lifecycle on testnet without enabling signed orders here",
    "Run at least 2 weeks of testnet execution in a separately approved enablement flow",
    "Manually review live unlock checklist before any live routing is considered",
]


def _status(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_data_health_healthy(data_health: dict[str, Any]) -> bool:
    return _status(data_health.get("status")) in {"HEALTHY", "PASSED", "OK"} or data_health.get("allow_trading") is True


def _is_risk_normal(risk: dict[str, Any]) -> bool:
    return _status(risk.get("status")) in {"NORMAL", "PASSED", "OK"} or risk.get("allow_new_position") is True


def _is_spreadsheet_sync_available(spreadsheet: dict[str, Any]) -> bool:
    status = _status(spreadsheet.get("status"))
    return status in {"OK", "PASSED", "EXPORTED_LOCAL_BACKUP", "SKIPPED"} or bool(spreadsheet)


def _is_step150_validation_passed(step150: dict[str, Any]) -> bool:
    return _status(step150.get("status")) == "PASSED"


def _build_checks(
    *,
    data_health: dict[str, Any],
    risk: dict[str, Any],
    spreadsheet: dict[str, Any],
    step150: dict[str, Any],
    live_readiness: dict[str, Any],
) -> dict[str, bool]:
    return {
        "data_health_healthy": _is_data_health_healthy(data_health),
        "risk_normal": _is_risk_normal(risk),
        "spreadsheet_sync_available": _is_spreadsheet_sync_available(spreadsheet),
        "step150_validation_passed": _is_step150_validation_passed(step150),
        "live_readiness_currently_blocked": live_readiness.get("ready") is False,
        "live_trading_disabled": True,
        "testnet_order_submission_disabled": True,
        "real_telegram_send_disabled": True,
        "external_order_submission_not_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED is False,
    }


def build_limited_live_readiness_report() -> dict[str, Any]:
    """Build the guarded limited-live readiness report.

    This module is intentionally read-only/review-only. It repairs the historical
    ``reports.limited_live_readiness`` operational surface while keeping the
    canonical implementation under ``crypto_ai_system.reports``. No live trading,
    testnet signed order submission, Telegram send, or config mutation is enabled.
    """
    data_health = read_json(DATA_HEALTH_PATH, {}) or {}
    risk = read_json(RISK_STATUS_PATH, {}) or {}
    spreadsheet = read_json(SPREADSHEET_SYNC_RESULT_PATH, {}) or {}
    step150 = read_json(STEP150_VALIDATION_PATH, {}) or {}

    live_readiness = run_live_readiness_check()
    if not live_readiness:
        live_readiness = read_json(LIVE_READINESS_PATH, {}) or {}

    checks = _build_checks(
        data_health=data_health,
        risk=risk,
        spreadsheet=spreadsheet,
        step150=step150,
        live_readiness=live_readiness,
    )
    checks_passed = [name for name, ok in checks.items() if ok]
    checks_failed = [name for name, ok in checks.items() if not ok]

    readiness_status = "READY_FOR_LIMITED_LIVE_REVIEW" if not checks_failed else "NOT_READY_FOR_LIMITED_LIVE"
    report = {
        "version": LIMITED_LIVE_READINESS_VERSION,
        "created_at": utc_now_iso(),
        "readiness_status": readiness_status,
        "checks": checks,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "max_live_position_usdt": MAX_LIVE_POSITION_USDT,
        "max_order_notional_usdt": MAX_ORDER_NOTIONAL_USDT,
        "required_next_steps": list(_REQUIRED_NEXT_STEPS),
        "source_paths": {
            "data_health": str(DATA_HEALTH_PATH),
            "risk": str(RISK_STATUS_PATH),
            "spreadsheet_sync": str(SPREADSHEET_SYNC_RESULT_PATH),
            "step150_validation": str(STEP150_VALIDATION_PATH),
            "live_readiness": str(LIVE_READINESS_PATH),
        },
        "safety": {
            "live_trading_allowed": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
            "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE,
            "real_telegram_send_allowed": REAL_TELEGRAM_SEND_ALLOWED_BY_THIS_MODULE,
            "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        },
        "live_readiness": live_readiness,
    }
    atomic_write_json(LIMITED_LIVE_READINESS_REPORT_PATH, report)
    log_event(
        "limited_live_readiness_report_created",
        {
            "readiness_status": readiness_status,
            "checks_failed": checks_failed,
            "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        },
    )
    return report


def main() -> None:
    report = build_limited_live_readiness_report()
    print(
        f"Limited live readiness: {report['readiness_status']} "
        f"passed={len(report['checks_passed'])} failed={len(report['checks_failed'])}"
    )


if __name__ == "__main__":
    main()
