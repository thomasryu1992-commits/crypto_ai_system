from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"

RUNTIME_GUARD_RESULT_PATH = STORAGE_DIR / "runtime_guard_result.json"
RUNTIME_GUARD_LOG_PATH = STORAGE_DIR / "runtime_guard_log.json"


ALLOWED_RUNTIME_MODES = {
    "OPERATIONAL_DRY_RUN",
    "PAPER_ONLY",
    "MOCK_EXECUTION_TEST",
    "LIVE_BLOCKED",
}


def run_runtime_guard(
    required_mode: Optional[str] = None,
    source: str = "manual",
    exit_on_block: bool = False,
) -> Dict[str, Any]:
    """
    Step 60:
    Runtime Safety Guard / Mode Controller

    Purpose:
    - Centralize runtime safety checks.
    - Prevent accidental live trading.
    - Prevent scheduled dry-run from executing with order flags enabled.
    - Save runtime_guard_result.json and runtime_guard_log.json.

    Modes:
    - OPERATIONAL_DRY_RUN:
      Real market data allowed.
      Telegram / Spreadsheet allowed.
      Mock or live order execution not allowed.

    - PAPER_ONLY:
      Paper trading allowed.
      Mock or live order execution not allowed.

    - MOCK_EXECUTION_TEST:
      Manual mock order testing allowed only when ALLOW_MOCK_ORDER_IN_MANUAL_TEST=true.
      Live trading must remain false.

    - LIVE_BLOCKED:
      Everything order-related must be disabled.

    LIVE mode is intentionally unsupported.
    """

    load_dotenv(PROJECT_ROOT / ".env")
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    started_at = _now_utc_iso()

    try:
        context = _read_runtime_context()
        checks = _run_checks(
            context=context,
            required_mode=required_mode,
        )

        blocked = any(check.get("passed") is not True for check in checks if check.get("severity") == "ERROR")
        warning_count = len([
            check for check in checks
            if check.get("passed") is not True and check.get("severity") == "WARNING"
        ])

        status = "BLOCKED" if blocked else ("PASSED_WITH_WARNINGS" if warning_count else "PASSED")

        result = {
            "step": "STEP_60_RUNTIME_GUARD",
            "status": status,
            "allowed": not blocked,
            "source": source,
            "started_at_utc": started_at,
            "finished_at_utc": _now_utc_iso(),
            "required_mode": required_mode,
            "runtime_mode": context.get("runtime_mode"),
            "context": context,
            "checks": checks,
            "failed_checks": [
                check for check in checks
                if check.get("passed") is not True
            ],
            "error_failures": [
                check for check in checks
                if check.get("passed") is not True and check.get("severity") == "ERROR"
            ],
            "warning_failures": [
                check for check in checks
                if check.get("passed") is not True and check.get("severity") == "WARNING"
            ],
            "files": {
                "runtime_guard_result": str(RUNTIME_GUARD_RESULT_PATH),
                "runtime_guard_log": str(RUNTIME_GUARD_LOG_PATH),
            },
        }

        _save_json(RUNTIME_GUARD_RESULT_PATH, result)
        _append_log(RUNTIME_GUARD_LOG_PATH, result)

        if exit_on_block and blocked:
            _print_result(result)
            raise SystemExit(1)

        return result

    except SystemExit:
        raise

    except Exception as error:
        error_result = {
            "step": "STEP_60_RUNTIME_GUARD",
            "status": "ERROR",
            "allowed": False,
            "source": source,
            "started_at_utc": started_at,
            "finished_at_utc": _now_utc_iso(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "files": {
                "runtime_guard_result": str(RUNTIME_GUARD_RESULT_PATH),
                "runtime_guard_log": str(RUNTIME_GUARD_LOG_PATH),
            },
        }

        _save_json(RUNTIME_GUARD_RESULT_PATH, error_result)
        _append_log(RUNTIME_GUARD_LOG_PATH, error_result)

        if exit_on_block:
            _print_result(error_result)
            raise SystemExit(1)

        return error_result


def assert_runtime_allowed(
    required_mode: Optional[str] = None,
    source: str = "manual",
) -> Dict[str, Any]:
    """
    Helper for other runners.

    Raises SystemExit(1) if runtime is blocked.
    """

    result = run_runtime_guard(
        required_mode=required_mode,
        source=source,
        exit_on_block=False,
    )

    if result.get("allowed") is not True:
        _print_result(result)
        raise SystemExit(1)

    return result


def _read_runtime_context() -> Dict[str, Any]:
    runtime_mode = os.getenv("RUNTIME_MODE", "OPERATIONAL_DRY_RUN").strip().upper()

    return {
        "runtime_mode": runtime_mode,
        "global_kill_switch": _env_bool("GLOBAL_KILL_SWITCH", False),
        "allow_mock_order_in_manual_test": _env_bool("ALLOW_MOCK_ORDER_IN_MANUAL_TEST", False),
        "allow_live_trading": _env_bool("ALLOW_LIVE_TRADING", False),
        "bot_mode": os.getenv("BOT_MODE", "PAPER_ONLY").strip().upper(),
        "exchange_mode": os.getenv("EXCHANGE_MODE", "MOCK").strip().upper(),
        "live_trading_enabled": _env_bool("LIVE_TRADING_ENABLED", False),
        "exchange_order_enabled": _env_bool("EXCHANGE_ORDER_ENABLED", False),
        "order_executor_integration_enabled": _env_bool("ORDER_EXECUTOR_INTEGRATION_ENABLED", False),
        "real_market_data_enabled": _env_bool("REAL_MARKET_DATA_ENABLED", False),
        "telegram_enabled": _env_bool("TELEGRAM_ENABLED", False),
        "spreadsheet_export_enabled": _env_bool("SPREADSHEET_EXPORT_ENABLED", False),
        "google_sheets_enabled": _env_bool("GOOGLE_SHEETS_ENABLED", False),
    }


def _run_checks(
    context: Dict[str, Any],
    required_mode: Optional[str],
) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    runtime_mode = context.get("runtime_mode")

    _add_check(
        checks,
        name="RUNTIME_MODE_SUPPORTED",
        passed=runtime_mode in ALLOWED_RUNTIME_MODES,
        severity="ERROR",
        message=(
            f"Runtime mode {runtime_mode} is supported."
            if runtime_mode in ALLOWED_RUNTIME_MODES
            else f"Runtime mode {runtime_mode} is not supported."
        ),
        details={
            "runtime_mode": runtime_mode,
            "allowed_modes": sorted(ALLOWED_RUNTIME_MODES),
        },
    )

    if required_mode:
        required = required_mode.strip().upper()

        _add_check(
            checks,
            name="REQUIRED_RUNTIME_MODE_MATCH",
            passed=runtime_mode == required,
            severity="ERROR",
            message=(
                f"Runtime mode matches required mode {required}."
                if runtime_mode == required
                else f"Runtime mode {runtime_mode} does not match required mode {required}."
            ),
            details={
                "runtime_mode": runtime_mode,
                "required_mode": required,
            },
        )

    _add_check(
        checks,
        name="GLOBAL_KILL_SWITCH_OFF",
        passed=context.get("global_kill_switch") is False,
        severity="ERROR",
        message=(
            "GLOBAL_KILL_SWITCH=false confirmed."
            if context.get("global_kill_switch") is False
            else "GLOBAL_KILL_SWITCH=true. Runtime is blocked."
        ),
        details=context,
    )

    _add_check(
        checks,
        name="ALLOW_LIVE_TRADING_FALSE",
        passed=context.get("allow_live_trading") is False,
        severity="ERROR",
        message=(
            "ALLOW_LIVE_TRADING=false confirmed."
            if context.get("allow_live_trading") is False
            else "ALLOW_LIVE_TRADING=true is not allowed in current system."
        ),
        details=context,
    )

    _add_check(
        checks,
        name="LIVE_TRADING_DISABLED",
        passed=context.get("live_trading_enabled") is False,
        severity="ERROR",
        message=(
            "LIVE_TRADING_ENABLED=false confirmed."
            if context.get("live_trading_enabled") is False
            else "LIVE_TRADING_ENABLED=true. Runtime is blocked."
        ),
        details=context,
    )

    _add_check(
        checks,
        name="EXCHANGE_MODE_MOCK_ONLY",
        passed=context.get("exchange_mode") == "MOCK",
        severity="ERROR",
        message=(
            "EXCHANGE_MODE=MOCK confirmed."
            if context.get("exchange_mode") == "MOCK"
            else f"EXCHANGE_MODE={context.get('exchange_mode')} is not allowed."
        ),
        details=context,
    )

    _add_mode_specific_checks(checks, context)

    return checks


def _add_mode_specific_checks(
    checks: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> None:
    runtime_mode = context.get("runtime_mode")

    if runtime_mode == "OPERATIONAL_DRY_RUN":
        _check_orders_disabled_for_dry_run(checks, context)

        _add_check(
            checks,
            name="REAL_MARKET_DATA_ALLOWED_FOR_DRY_RUN",
            passed=True,
            severity="INFO",
            message="Real market data is allowed in OPERATIONAL_DRY_RUN.",
            details={
                "real_market_data_enabled": context.get("real_market_data_enabled"),
            },
        )

        _add_check(
            checks,
            name="TELEGRAM_SPREADSHEET_ALLOWED_FOR_DRY_RUN",
            passed=True,
            severity="INFO",
            message="Telegram and Spreadsheet integrations are allowed in OPERATIONAL_DRY_RUN.",
            details={
                "telegram_enabled": context.get("telegram_enabled"),
                "spreadsheet_export_enabled": context.get("spreadsheet_export_enabled"),
                "google_sheets_enabled": context.get("google_sheets_enabled"),
            },
        )

        return

    if runtime_mode == "PAPER_ONLY":
        _check_orders_disabled_for_dry_run(checks, context)

        _add_check(
            checks,
            name="PAPER_ONLY_BOT_MODE",
            passed=context.get("bot_mode") == "PAPER_ONLY",
            severity="ERROR",
            message=(
                "BOT_MODE=PAPER_ONLY confirmed."
                if context.get("bot_mode") == "PAPER_ONLY"
                else f"BOT_MODE={context.get('bot_mode')} is not PAPER_ONLY."
            ),
            details=context,
        )

        return

    if runtime_mode == "LIVE_BLOCKED":
        _check_orders_disabled_for_dry_run(checks, context)

        _add_check(
            checks,
            name="LIVE_BLOCKED_MODE_ACTIVE",
            passed=True,
            severity="INFO",
            message="LIVE_BLOCKED mode active. All order routes must remain disabled.",
            details=context,
        )

        return

    if runtime_mode == "MOCK_EXECUTION_TEST":
        allow_mock = context.get("allow_mock_order_in_manual_test") is True

        _add_check(
            checks,
            name="MOCK_TEST_EXPLICITLY_ALLOWED",
            passed=allow_mock,
            severity="ERROR",
            message=(
                "ALLOW_MOCK_ORDER_IN_MANUAL_TEST=true confirmed."
                if allow_mock
                else "ALLOW_MOCK_ORDER_IN_MANUAL_TEST must be true for MOCK_EXECUTION_TEST."
            ),
            details=context,
        )

        _add_check(
            checks,
            name="MOCK_TEST_LIVE_TRADING_DISABLED",
            passed=context.get("live_trading_enabled") is False,
            severity="ERROR",
            message="Live trading remains disabled during mock execution test.",
            details=context,
        )

        _add_check(
            checks,
            name="MOCK_TEST_EXCHANGE_MODE_MOCK",
            passed=context.get("exchange_mode") == "MOCK",
            severity="ERROR",
            message=f"EXCHANGE_MODE={context.get('exchange_mode')}.",
            details=context,
        )

        return


def _check_orders_disabled_for_dry_run(
    checks: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> None:
    _add_check(
        checks,
        name="EXCHANGE_ORDER_DISABLED",
        passed=context.get("exchange_order_enabled") is False,
        severity="ERROR",
        message=(
            "EXCHANGE_ORDER_ENABLED=false confirmed."
            if context.get("exchange_order_enabled") is False
            else "EXCHANGE_ORDER_ENABLED=true is not allowed in this runtime mode."
        ),
        details=context,
    )

    _add_check(
        checks,
        name="ORDER_EXECUTOR_BRIDGE_DISABLED",
        passed=context.get("order_executor_integration_enabled") is False,
        severity="ERROR",
        message=(
            "ORDER_EXECUTOR_INTEGRATION_ENABLED=false confirmed."
            if context.get("order_executor_integration_enabled") is False
            else "ORDER_EXECUTOR_INTEGRATION_ENABLED=true is not allowed in this runtime mode."
        ),
        details=context,
    )


def _add_check(
    checks: List[Dict[str, Any]],
    name: str,
    passed: bool,
    severity: str,
    message: str,
    details: Optional[Any] = None,
) -> None:
    checks.append({
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "message": message,
        "details": details if details is not None else {},
        "timestamp_utc": _now_utc_iso(),
    })


def _print_result(result: Dict[str, Any]) -> None:
    print("=" * 90)
    print("[RUNTIME GUARD]")
    print("=" * 90)
    print(f"Status: {result.get('status')}")
    print(f"Allowed: {result.get('allowed')}")
    print(f"Runtime Mode: {result.get('runtime_mode')}")
    print(f"Required Mode: {result.get('required_mode')}")

    failed_checks = result.get("failed_checks", [])

    print("-" * 90)
    print("[FAILED CHECKS]")

    if failed_checks:
        for check in failed_checks:
            print(f"- {check.get('severity')} / {check.get('name')}: {check.get('message')}")
    else:
        print("None")

    print("-" * 90)
    print("[FILES]")
    for key, value in _safe_dict(result.get("files")).items():
        print(f"{key}: {value}")

    print("=" * 90)


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)

    if value is None:
        return default

    return value.strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
        "on",
    }


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _append_log(path: Path, item: Dict[str, Any], max_items: int = 500) -> None:
    existing = _load_json(path, default=[])

    if not isinstance(existing, list):
        existing = []

    existing.append(item)
    existing = existing[-max_items:]

    _save_json(path, existing)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    result = run_runtime_guard(
        required_mode=None,
        source="cli",
        exit_on_block=False,
    )

    _print_result(result)

    if result.get("allowed") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()