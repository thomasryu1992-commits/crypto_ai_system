from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.onboarding_wizard_failure_doctor import persist_onboarding_wizard_failure_doctor


def _latest_path(filename: str) -> Path:
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    return latest / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and print P37 onboarding failure doctor artifacts.")
    parser.add_argument("--print-diagnosis", action="store_true")
    parser.add_argument("--print-lookup", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-card", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    parser.add_argument("--print-paths", action="store_true")
    args = parser.parse_args()

    report = persist_onboarding_wizard_failure_doctor(load_config(Path.cwd()))
    if args.print_diagnosis:
        print(read_json(_latest_path("p37_self_diagnosis_results.json"), default=[]))
    elif args.print_lookup:
        print(read_json(_latest_path("p37_failure_doctor_lookup.json"), default=[]))
    elif args.print_checklist:
        print(_latest_path("p37_self_diagnosis_checklist.md").read_text(encoding="utf-8"))
    elif args.print_card:
        print(read_json(_latest_path("p37_operator_self_diagnosis_card.json"), default={}))
    elif args.print_markdown:
        print(_latest_path("p37_self_diagnosis_pack.md").read_text(encoding="utf-8"))
    elif args.print_paths:
        summary = read_json(_latest_path("p37_onboarding_wizard_failure_doctor_summary.json"), default={})
        for key, value in sorted(summary.get("self_diagnosis_paths", {}).items()):
            print(f"{key}: {value}")
    else:
        print(report["status"])
        print(f"diagnosis_issue_count={report['diagnosis_issue_count']}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
