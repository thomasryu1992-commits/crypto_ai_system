from __future__ import annotations

from crypto_ai_system.execution.external_runtime_signed_testnet_evidence_acquisition import (
    persist_p58_external_runtime_evidence_acquisition,
)


if __name__ == "__main__":
    report = persist_p58_external_runtime_evidence_acquisition()
    print(report["status"])
    print(report["p58_external_runtime_evidence_acquisition_sha256"])
