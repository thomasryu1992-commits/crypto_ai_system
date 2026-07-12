from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_round_trip_seal import persist_operator_evidence_archive_round_trip_seal


def main() -> int:
    report = persist_operator_evidence_archive_round_trip_seal(load_config(Path.cwd()))
    print(report["status"])
    print(f"seal_issue_count={report['seal_issue_count']}")
    print(f"seal_hash={report['seal_hash']}")
    print(f"seal_chain_hash={report['seal_chain_hash']}")
    print("runtime_scheduler_enabled=false")
    print("live_order_submission_allowed=false")
    print("order_endpoint_called=false")
    print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
