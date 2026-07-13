from __future__ import annotations

from crypto_ai_system.execution.operator_side_external_order_test_execution_kit import (
    persist_p62_operator_side_external_order_test_execution_kit,
)

if __name__ == "__main__":
    report = persist_p62_operator_side_external_order_test_execution_kit()
    print(report["status"])
    print(report["p62_operator_side_external_order_test_execution_kit_sha256"])
