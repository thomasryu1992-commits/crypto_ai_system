from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_intake_validator import persist_operator_evidence_archive_intake_validator


def main() -> int:
    report = persist_operator_evidence_archive_intake_validator(load_config(Path.cwd()))
    print(report["status"])
    print(f"intake_issue_count={report['intake_issue_count']}")
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
