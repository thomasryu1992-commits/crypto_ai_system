from __future__ import annotations

from crypto_ai_system.execution.concrete_external_order_test_executor_integration import (
    persist_p63_concrete_external_order_test_executor_integration,
)

if __name__ == "__main__":
    report = persist_p63_concrete_external_order_test_executor_integration()
    print(report["status"])
    print(report["p63_concrete_external_order_test_executor_integration_sha256"])
