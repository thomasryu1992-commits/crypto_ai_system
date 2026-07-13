from __future__ import annotations

import json

from crypto_ai_system.execution.signed_testnet_one_order_runtime_package import persist_signed_testnet_one_order_runtime_package


if __name__ == "__main__":
    report = persist_signed_testnet_one_order_runtime_package()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
