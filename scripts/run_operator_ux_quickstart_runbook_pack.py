from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_ux_quickstart_runbook_pack import persist_operator_ux_quickstart_runbook_pack


def _latest_path(filename: str) -> Path:
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    return latest / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and print P35 non-developer operator quickstart artifacts.")
    parser.add_argument("--print-runbook", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-safe-commands", action="store_true")
    parser.add_argument("--print-text", action="store_true")
    parser.add_argument("--print-paths", action="store_true")
    args = parser.parse_args()
    report = persist_operator_ux_quickstart_runbook_pack(load_config(Path.cwd()))
    if args.print_runbook:
        print(_latest_path("p35_operator_ux_quickstart_runbook.md").read_text(encoding="utf-8"))
    elif args.print_checklist:
        print(_latest_path("p35_operator_ux_checklist.md").read_text(encoding="utf-8"))
    elif args.print_safe_commands:
        print(_latest_path("p35_safe_command_guide.md").read_text(encoding="utf-8"))
    elif args.print_text:
        print(_latest_path("p35_operator_ux_quickstart.txt").read_text(encoding="utf-8"))
    elif args.print_paths:
        summary = read_json(_latest_path("p35_operator_ux_quickstart_runbook_pack_summary.json"), default={})
        for key, value in sorted(summary.get("quickstart_paths", {}).items()):
            print(f"{key}: {value}")
    else:
        print(report["status"])
        print("limited_live_scaled_auto_trading_allowed=false")
        print("runtime_scheduler_enabled=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
