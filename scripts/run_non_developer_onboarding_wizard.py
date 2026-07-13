from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.non_developer_onboarding_wizard import persist_non_developer_onboarding_wizard


def _latest_path(filename: str) -> Path:
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    return latest / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and print P36 non-developer onboarding wizard artifacts.")
    parser.add_argument("--print-wizard", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-failures", action="store_true")
    parser.add_argument("--print-card", action="store_true")
    parser.add_argument("--print-steps", action="store_true")
    parser.add_argument("--print-paths", action="store_true")
    args = parser.parse_args()

    report = persist_non_developer_onboarding_wizard(load_config(Path.cwd()))
    if args.print_wizard:
        print(_latest_path("p36_zip_drop_in_wizard.md").read_text(encoding="utf-8"))
    elif args.print_checklist:
        print(_latest_path("p36_zip_drop_in_checklist.md").read_text(encoding="utf-8"))
    elif args.print_failures:
        print(_latest_path("p36_failure_message_lookup.md").read_text(encoding="utf-8"))
    elif args.print_card:
        print(read_json(_latest_path("p36_operator_onboarding_card.json"), default={}))
    elif args.print_steps:
        print(read_json(_latest_path("p36_onboarding_wizard_steps.json"), default=[]))
    elif args.print_paths:
        summary = read_json(_latest_path("p36_non_developer_onboarding_wizard_summary.json"), default={})
        for key, value in sorted(summary.get("onboarding_paths", {}).items()):
            print(f"{key}: {value}")
    else:
        print(report["status"])
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
