from __future__ import annotations

from crypto_ai_system.execution.external_evidence_import_validator import persist_p50_external_evidence_import_validator


if __name__ == "__main__":
    report = persist_p50_external_evidence_import_validator()
    print(report["status"])
    print(report["p50_external_evidence_import_validator_sha256"])
