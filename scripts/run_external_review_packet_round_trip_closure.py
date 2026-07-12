from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_external_review_packet_round_trip_closure import persist_external_review_packet_round_trip_closure


def _latest_path(filename: str) -> Path:
    return Path.cwd() / "storage" / "latest" / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P45 external review packet round-trip closure / reviewer acceptance template.")
    parser.add_argument("--print-template", action="store_true")
    parser.add_argument("--print-validation", action="store_true")
    parser.add_argument("--print-chain", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    args = parser.parse_args()

    report = persist_external_review_packet_round_trip_closure(load_config(Path.cwd()))
    if args.print_template:
        print(read_json(_latest_path("p45_reviewer_acceptance_template.json"), default={}))
    elif args.print_validation:
        print(read_json(_latest_path("p45_reviewer_acceptance_validation_results.json"), default={}))
    elif args.print_chain:
        print(read_json(_latest_path("p45_external_review_packet_closure_chain.json"), default={}))
    elif args.print_checklist:
        print(_latest_path("p45_reviewer_acceptance_checklist.md").read_text(encoding="utf-8"))
    elif args.print_summary:
        print(read_json(_latest_path("p45_external_review_packet_round_trip_closure_summary.json"), default={}))
    elif args.print_markdown:
        print(_latest_path("p45_external_review_packet_round_trip_closure.md").read_text(encoding="utf-8"))
    else:
        print(report["status"])
        print(f"closure_issue_count={report['closure_issue_count']}")
        print(f"reviewer_decision={report['reviewer_decision']}")
        print(f"template_hash={report['template_hash']}")
        print(f"closure_chain_hash={report['closure_chain_hash']}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
