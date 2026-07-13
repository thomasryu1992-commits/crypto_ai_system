from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.runtime_release_gate_operator_handoff import (
    STATUS_BLOCKED_FAIL_CLOSED,
    persist_runtime_release_gate_operator_handoff,
)


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_runtime_release_gate_operator_handoff(cfg=cfg)
    print(report["status"])
    print(report["p17_runtime_release_gate_operator_handoff_sha256"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("live_scaled_execution_enabled=false")
    print("live_order_submission_allowed=false")
    return 1 if report["status"] == STATUS_BLOCKED_FAIL_CLOSED else 0


if __name__ == "__main__":
    raise SystemExit(main())
