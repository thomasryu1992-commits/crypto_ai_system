from __future__ import annotations

from core.console import configure_utf8_console, safe_print
from notify.telegram_notifier import send_telegram_message
from system_guard.scheduler_health import check_scheduler_health


def main() -> None:
    configure_utf8_console()
    health = check_scheduler_health()
    message = f"Scheduler Health: {health.get('status')} / errors={health.get('error_failures')}"
    result = send_telegram_message(message)
    safe_print("Scheduler health report:", result)


if __name__ == "__main__":
    main()
