from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_intake_validator import persist_operator_evidence_archive_intake_validator


def _latest_path(filename: str) -> Path:
    return Path.cwd() / "storage" / "latest" / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P42 operator evidence archive intake validator / hash recheck pack.")
    parser.add_argument("--print-validation", action="store_true")
    parser.add_argument("--print-chain", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    args = parser.parse_args()

    report = persist_operator_evidence_archive_intake_validator(load_config(Path.cwd()))
    if args.print_validation:
        print(read_json(_latest_path("p42_operator_evidence_archive_intake_validation_results.json"), default={}))
    elif args.print_chain:
        print(read_json(_latest_path("p42_operator_evidence_archive_hash_recheck_chain.json"), default={}))
    elif args.print_checklist:
        print(_latest_path("p42_operator_evidence_archive_intake_checklist.md").read_text(encoding="utf-8"))
    elif args.print_summary:
        print(read_json(_latest_path("p42_operator_evidence_archive_intake_validator_summary.json"), default={}))
    elif args.print_markdown:
        print(_latest_path("p42_operator_evidence_archive_intake_validator.md").read_text(encoding="utf-8"))
    else:
        print(report["status"])
        print(f"intake_issue_count={report['intake_issue_count']}")
        print(f"archive_index_hash_mismatch={str(report['archive_index_hash_mismatch']).lower()}")
        print(f"audit_trail_chain_hash_mismatch={str(report['audit_trail_chain_hash_mismatch']).lower()}")
        print(f"archive_entry_hash_mismatch_count={report['archive_entry_hash_mismatch_count']}")
        print(f"missing_p41_artifact_count={report['missing_p41_artifact_count']}")
        print(f"hash_recheck_chain_hash={report['hash_recheck_chain_hash']}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
