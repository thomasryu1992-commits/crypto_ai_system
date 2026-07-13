from __future__ import annotations

from core.console import configure_utf8_console, safe_print
from core.json_io import write_storage_json
from notify.telegram_notifier import send_telegram_message
from system_guard.scheduler_health import check_scheduler_health


def _format_failed_checks(health: dict) -> str:
    failed = [c for c in health.get("checks", []) if c.get("status") in {"MISSING", "FAILED", "WARNING"}]
    if not failed:
        return "None"
    lines = []
    for item in failed[:10]:
        line = f"- {item.get('file')}: {item.get('status')}"
        if item.get("reason"):
            line += f" ({item.get('reason')})"
        if item.get("message"):
            line += f" ({item.get('message')})"
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    configure_utf8_console()
    health = check_scheduler_health()
    message = (
        f"Scheduler Health: {health.get('status')} / errors={health.get('error_failures')} "
        f"/ warnings={health.get('warning_failures')}\n"
        f"Failed checks:\n{_format_failed_checks(health)}"
    )
    result = send_telegram_message(message)
    # Keep legacy scheduler health compatible: write the Telegram result to latest storage.
    write_storage_json("telegram_alert_result.json", result)
    safe_print("Scheduler health report:", result)
    safe_print("Scheduler health detail:", health)


if __name__ == "__main__":
    main()
