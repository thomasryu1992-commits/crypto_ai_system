from __future__ import annotations

import json

from core.console import configure_utf8_console, safe_print
from system_guard.scheduler_health import check_scheduler_health


def main() -> None:
    configure_utf8_console()
    health = check_scheduler_health()
    safe_print(json.dumps(health, indent=2, ensure_ascii=False, default=str))
    if health.get("status") != "HEALTHY":
        safe_print("\nFailed checks:")
        for item in health.get("checks", []):
            if item.get("status") not in {"OK", "SKIPPED"}:
                safe_print(f"- {item.get('file')}: {item.get('status')} {item.get('reason') or item.get('message') or ''}")


if __name__ == "__main__":
    main()
