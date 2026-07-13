from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_dashboard_command_contract import persist_telegram_launcher_dashboard_command_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P32 Telegram/Launcher dashboard command contract gate.")
    parser.add_argument("--print-contract", action="store_true", help="Print command contract JSON.")
    parser.add_argument("--print-telegram-status", action="store_true", help="Print Telegram status response.")
    parser.add_argument("--print-launcher", action="store_true", help="Print Launcher command payload JSON.")
    parser.add_argument("--print-export-paths", action="store_true", help="Print export paths response JSON.")
    args = parser.parse_args()
    report = persist_telegram_launcher_dashboard_command_contract(load_config(Path.cwd()))
    if args.print_contract:
        print(json.dumps(report["command_contract"], indent=2, sort_keys=True))
        return 0 if not report.get("blocked") else 1
    if args.print_telegram_status:
        print(report["telegram_text_responses"]["status"])
        return 0 if not report.get("blocked") else 1
    if args.print_launcher:
        print(json.dumps(report["launcher_command_payload"], indent=2, sort_keys=True))
        return 0 if not report.get("blocked") else 1
    if args.print_export_paths:
        print(json.dumps(report["command_responses"]["export_paths"], indent=2, sort_keys=True))
        return 0 if not report.get("blocked") else 1
    print(report["status"])
    print(f"allowed_command_count={report['allowed_command_count']}")
    print(f"contract_command_count={report['contract_command_count']}")
    print(f"live_scaled_execution_enabled={str(report['live_scaled_execution_enabled']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")
    print(f"live_order_submission_allowed={str(report['live_order_submission_allowed']).lower()}")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
