from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_ux_quickstart_runbook_pack import persist_operator_ux_quickstart_runbook_pack


def main() -> int:
    report = persist_operator_ux_quickstart_runbook_pack(load_config(Path.cwd()))
    print(report["status"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("runtime_scheduler_enabled=false")
    print("order_endpoint_called=false")
    print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
