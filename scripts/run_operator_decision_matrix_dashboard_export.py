from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_decision_matrix_dashboard_export import persist_operator_decision_matrix_dashboard_export


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P31 operator decision matrix dashboard export.")
    parser.add_argument("--print-dashboard", action="store_true", help="Print compact dashboard JSON.")
    parser.add_argument("--print-telegram", action="store_true", help="Print Telegram-friendly dashboard summary.")
    parser.add_argument("--print-markdown-path", action="store_true", help="Print generated dashboard Markdown path.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_operator_decision_matrix_dashboard_export(cfg)
    if args.print_dashboard:
        print(json.dumps(report["compact_dashboard"], indent=2, sort_keys=True))
        return 0 if not report.get("blocked") else 1
    if args.print_telegram:
        print(report["telegram_summary_text"])
        return 0 if not report.get("blocked") else 1
    if args.print_markdown_path:
        print(str((cfg.root / "storage" / "latest" / "p31_operator_decision_matrix_dashboard.md").resolve()))
        return 0 if not report.get("blocked") else 1
    print(report["status"])
    print(f"operator_final_activation_decision={report['operator_final_activation_decision']}")
    print(f"live_scaled_execution_enabled={str(report['live_scaled_execution_enabled']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")
    print(f"live_order_submission_allowed={str(report['live_order_submission_allowed']).lower()}")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
