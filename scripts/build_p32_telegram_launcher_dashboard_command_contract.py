from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_dashboard_command_contract import persist_telegram_launcher_dashboard_command_contract


def main() -> int:
    report = persist_telegram_launcher_dashboard_command_contract(load_config(Path.cwd()))
    print(report["status"])
    print(f"allowed_command_count={report['allowed_command_count']}")
    print(f"contract_command_count={report['contract_command_count']}")
    print(f"live_scaled_execution_enabled={str(report['live_scaled_execution_enabled']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")
    print(f"live_order_submission_allowed={str(report['live_order_submission_allowed']).lower()}")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
