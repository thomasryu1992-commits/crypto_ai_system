from __future__ import annotations

from crypto_ai_system.execution.real_testnet_order_test_dry_validation_adapter import (
    persist_p61_real_testnet_order_test_dry_validation_adapter,
)

if __name__ == "__main__":
    report = persist_p61_real_testnet_order_test_dry_validation_adapter()
    print(report["status"])
    print(report["p61_real_testnet_order_test_dry_validation_adapter_sha256"])
