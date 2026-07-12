from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.non_developer_onboarding_wizard import persist_non_developer_onboarding_wizard


def main() -> int:
    report = persist_non_developer_onboarding_wizard(load_config(Path.cwd()))
    print(report["status"])
    print("runtime_scheduler_enabled=false")
    print("order_endpoint_called=false")
    print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
