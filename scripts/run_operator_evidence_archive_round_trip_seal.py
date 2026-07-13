from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_round_trip_seal import persist_operator_evidence_archive_round_trip_seal


def _latest_path(filename: str) -> Path:
    return Path.cwd() / "storage" / "latest" / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P43 operator evidence archive round-trip seal / external review packet.")
    parser.add_argument("--print-packet", action="store_true")
    parser.add_argument("--print-chain", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    args = parser.parse_args()

    report = persist_operator_evidence_archive_round_trip_seal(load_config(Path.cwd()))
    if args.print_packet:
        print(read_json(_latest_path("p43_operator_evidence_archive_external_review_packet.json"), default={}))
    elif args.print_chain:
        print(read_json(_latest_path("p43_operator_evidence_archive_round_trip_seal_chain.json"), default={}))
    elif args.print_checklist:
        print(_latest_path("p43_operator_evidence_archive_round_trip_seal_checklist.md").read_text(encoding="utf-8"))
    elif args.print_summary:
        print(read_json(_latest_path("p43_operator_evidence_archive_round_trip_seal_summary.json"), default={}))
    elif args.print_markdown:
        print(_latest_path("p43_operator_evidence_archive_external_review_packet.md").read_text(encoding="utf-8"))
    else:
        print(report["status"])
        print(f"seal_issue_count={report['seal_issue_count']}")
        print(f"seal_hash={report['seal_hash']}")
        print(f"seal_chain_hash={report['seal_chain_hash']}")
        print(f"p41_status={report['p41_status']}")
        print(f"p42_status={report['p42_status']}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
