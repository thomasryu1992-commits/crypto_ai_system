from __future__ import annotations

from crypto_ai_system.execution.post_submit_evidence_intake import persist_post_submit_evidence_intake


if __name__ == "__main__":
    report = persist_post_submit_evidence_intake()
    print(report["status"])
    print(report["p7_post_submit_evidence_intake_sha256"])
