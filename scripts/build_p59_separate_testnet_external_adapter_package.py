from __future__ import annotations

from crypto_ai_system.execution.separate_testnet_external_adapter_package import (
    persist_p59_separate_testnet_external_adapter_package,
)

if __name__ == "__main__":
    report = persist_p59_separate_testnet_external_adapter_package()
    print(report["status"])
    print(report["p59_separate_testnet_external_adapter_package_sha256"])
