from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_support_bundle_intake_validator import persist_operator_support_bundle_intake_validator


def _latest_path(filename: str) -> Path:
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    return latest / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate P39 operator support bundle intake packet.")
    parser.add_argument("--print-validation", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    report = persist_operator_support_bundle_intake_validator(load_config(Path.cwd()))
    if args.print_validation:
        print(read_json(_latest_path("p39_operator_support_bundle_intake_validation_results.json"), default={}))
    elif args.print_checklist:
        print(_latest_path("p39_operator_support_bundle_intake_checklist.md").read_text(encoding="utf-8"))
    elif args.print_markdown:
        print(_latest_path("p39_operator_support_bundle_intake_validator.md").read_text(encoding="utf-8"))
    elif args.print_summary:
        print(read_json(_latest_path("p39_operator_support_bundle_intake_validator_summary.json"), default={}))
    else:
        print(report["status"])
        print(f"intake_issue_count={report['intake_issue_count']}")
        print(f"hash_mismatch_count={report['hash_mismatch_count']}")
        print(f"secret_detected={str(report['secret_detected']).lower()}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
