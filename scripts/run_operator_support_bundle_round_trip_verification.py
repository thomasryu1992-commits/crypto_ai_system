from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_support_bundle_round_trip_verification import persist_operator_support_bundle_round_trip_verification


def _latest_path(filename: str) -> Path:
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    return latest / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify P38 export -> P39 intake round-trip hash chain.")
    parser.add_argument("--print-chain", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    report = persist_operator_support_bundle_round_trip_verification(load_config(Path.cwd()))
    if args.print_chain:
        print(read_json(_latest_path("p40_operator_support_bundle_round_trip_chain.json"), default={}))
    elif args.print_checklist:
        print(_latest_path("p40_operator_support_bundle_round_trip_checklist.md").read_text(encoding="utf-8"))
    elif args.print_markdown:
        print(_latest_path("p40_operator_support_bundle_round_trip_verification.md").read_text(encoding="utf-8"))
    elif args.print_summary:
        print(read_json(_latest_path("p40_operator_support_bundle_round_trip_verification_summary.json"), default={}))
    else:
        print(report["status"])
        print(f"round_trip_issue_count={report['round_trip_issue_count']}")
        print(f"round_trip_hash={report['round_trip_hash']}")
        print(f"secret_detected={str(report['secret_detected']).lower()}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
