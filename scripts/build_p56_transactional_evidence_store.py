from __future__ import annotations

from crypto_ai_system.execution.transactional_evidence_store import (
    persist_p56_transactional_evidence_store,
)


if __name__ == "__main__":
    report = persist_p56_transactional_evidence_store()
    print(report["status"])
    print(report["p56_transactional_evidence_store_sha256"])
