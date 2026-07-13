from __future__ import annotations

from crypto_ai_system.execution.transactional_p7_importer_integration import (
    persist_p57_transactional_p7_importer_integration,
)


if __name__ == "__main__":
    report = persist_p57_transactional_p7_importer_integration()
    print(report["status"])
    print(report["p57_transactional_p7_importer_integration_sha256"])
