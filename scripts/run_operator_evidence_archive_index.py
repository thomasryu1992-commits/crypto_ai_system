from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_index_audit_trail import persist_operator_evidence_archive_index


def _latest_path(filename: str) -> Path:
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    return latest / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Build P41 operator evidence archive index and audit trail pack.")
    parser.add_argument("--print-index", action="store_true")
    parser.add_argument("--print-chain", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-csv", action="store_true")
    args = parser.parse_args()

    report = persist_operator_evidence_archive_index(load_config(Path.cwd()))
    if args.print_index:
        print(read_json(_latest_path("p41_operator_evidence_archive_index.json"), default=[]))
    elif args.print_chain:
        print(read_json(_latest_path("p41_operator_evidence_audit_trail_chain.json"), default={}))
    elif args.print_checklist:
        print(_latest_path("p41_operator_evidence_archive_checklist.md").read_text(encoding="utf-8"))
    elif args.print_markdown:
        print(_latest_path("p41_operator_evidence_audit_trail.md").read_text(encoding="utf-8"))
    elif args.print_summary:
        print(read_json(_latest_path("p41_operator_evidence_archive_index_summary.json"), default={}))
    elif args.print_csv:
        print(_latest_path("p41_operator_evidence_archive_index.csv").read_text(encoding="utf-8"))
    else:
        print(report["status"])
        print(f"archive_issue_count={report['archive_issue_count']}")
        print(f"expected_archive_artifact_count={report['expected_archive_artifact_count']}")
        print(f"present_archive_artifact_count={report['present_archive_artifact_count']}")
        print(f"missing_archive_artifact_count={report['missing_archive_artifact_count']}")
        print(f"archive_index_hash={report['archive_index_hash']}")
        print(f"audit_trail_chain_hash={report['audit_trail_chain_hash']}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
