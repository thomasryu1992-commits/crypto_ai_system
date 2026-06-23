from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from notifiers.telegram_sender import send_telegram_message


PROJECT_ROOT = Path(__file__).resolve().parent
STORAGE_DIR = PROJECT_ROOT / "storage"

SCHEDULER_HEALTH_RESULT_PATH = STORAGE_DIR / "scheduler_health_result.json"
SCHEDULER_HEALTH_TELEGRAM_RESULT_PATH = STORAGE_DIR / "scheduler_health_telegram_result.json"
SCHEDULER_HEALTH_TELEGRAM_LOG_PATH = STORAGE_DIR / "scheduler_health_telegram_log.json"


def main() -> None:
    started_at = _now_utc_iso()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        enabled = _env_bool("SCHEDULER_HEALTH_TELEGRAM_ENABLED", True)

        if not enabled:
            result = {
                "step": "STEP_59_SCHEDULER_HEALTH_TELEGRAM_ALERT",
                "status": "SKIPPED",
                "sent": False,
                "enabled": False,
                "reason": "SCHEDULER_HEALTH_TELEGRAM_ENABLED=false",
                "timestamp_utc": started_at,
            }

            _save_json(SCHEDULER_HEALTH_TELEGRAM_RESULT_PATH, result)
            _append_log(SCHEDULER_HEALTH_TELEGRAM_LOG_PATH, result)
            _print_result(result)
            return

        run_check_first = _env_bool("SCHEDULER_HEALTH_RUN_CHECK_BEFORE_SEND", True)

        if run_check_first:
            check_process = subprocess.run(
                [sys.executable, "check_scheduler_health.py"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        else:
            check_process = None

        health_result = _load_json(SCHEDULER_HEALTH_RESULT_PATH, default={})

        message = _build_health_message(health_result)

        sender_result = send_telegram_message(message)

        result = {
            "step": "STEP_59_SCHEDULER_HEALTH_TELEGRAM_ALERT",
            "status": "SENT" if sender_result.get("sent") else "SKIPPED",
            "sent": sender_result.get("sent"),
            "enabled": sender_result.get("enabled"),
            "timestamp_utc": _now_utc_iso(),
            "health_status": health_result.get("status"),
            "sender_result": sender_result,
            "message_preview": message[:1000],
            "health_result_path": str(SCHEDULER_HEALTH_RESULT_PATH),
            "check_process": (
                {
                    "return_code": check_process.returncode,
                    "stdout_tail": _tail_text(check_process.stdout),
                    "stderr_tail": _tail_text(check_process.stderr),
                }
                if check_process is not None
                else None
            ),
        }

        _save_json(SCHEDULER_HEALTH_TELEGRAM_RESULT_PATH, result)
        _append_log(SCHEDULER_HEALTH_TELEGRAM_LOG_PATH, result)

        _print_result(result)

        if result.get("status") not in {"SENT", "SKIPPED"}:
            raise SystemExit(1)

    except Exception as error:
        error_result = {
            "step": "STEP_59_SCHEDULER_HEALTH_TELEGRAM_ALERT",
            "status": "FAILED",
            "sent": False,
            "timestamp_utc": started_at,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        }

        _save_json(SCHEDULER_HEALTH_TELEGRAM_RESULT_PATH, error_result)
        _append_log(SCHEDULER_HEALTH_TELEGRAM_LOG_PATH, error_result)

        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        raise SystemExit(1)


def _build_health_message(health_result: Dict[str, Any]) -> str:
    status = health_result.get("status", "UNKNOWN")
    summary = _safe_dict(health_result.get("summary"))

    emoji = {
        "HEALTHY": "✅",
        "WARNING": "⚠️",
        "UNHEALTHY": "🚨",
        "ERROR": "🚨",
    }.get(status, "ℹ️")

    failed_checks = health_result.get("failed_checks", [])
    if not isinstance(failed_checks, list):
        failed_checks = []

    lines = [
        f"{emoji} Crypto AI Scheduler Health",
        "",
        f"Status: {status}",
        f"Operational Dry Run: {summary.get('operational_status')}",
        f"Trading Cycle: {summary.get('trading_status')}",
        f"Spreadsheet: {summary.get('spreadsheet_status')}",
        f"Telegram: {summary.get('telegram_status')}",
        f"Current Price: {summary.get('current_price')}",
        "",
        f"Total Checks: {summary.get('total_checks')}",
        f"Error Failures: {summary.get('error_failures')}",
        f"Warning Failures: {summary.get('warning_failures')}",
        "",
        f"Checked At UTC: {health_result.get('finished_at_utc')}",
    ]

    if failed_checks:
        lines.append("")
        lines.append("Failed Checks:")

        for check in failed_checks[:8]:
            lines.append(
                f"- {check.get('severity')} / {check.get('name')}: {check.get('message')}"
            )

        if len(failed_checks) > 8:
            lines.append(f"- ...and {len(failed_checks) - 8} more")

    else:
        lines.append("")
        lines.append("Failed Checks: None")

    return "\n".join(lines)


def _print_result(result: Dict[str, Any]) -> None:
    print("=" * 90)
    print("[SCHEDULER HEALTH TELEGRAM ALERT]")
    print("=" * 90)
    print(f"Status: {result.get('status')}")
    print(f"Sent: {result.get('sent')}")
    print(f"Enabled: {result.get('enabled')}")
    print(f"Health Status: {result.get('health_status')}")
    print(f"Result Path: {SCHEDULER_HEALTH_TELEGRAM_RESULT_PATH}")
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


def _tail_text(text: str, max_lines: int = 80) -> str:
    if not text:
        return ""

    return "\n".join(text.splitlines()[-max_lines:])


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


if __name__ == "__main__":
    main()