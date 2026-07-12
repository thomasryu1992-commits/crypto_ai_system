from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_index_audit_trail import persist_operator_evidence_archive_index


def main() -> int:
    report = persist_operator_evidence_archive_index(load_config(Path.cwd()))
    print(report["status"])
    print(f"archive_issue_count={report['archive_issue_count']}")
    print(f"archive_index_hash={report['archive_index_hash']}")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
