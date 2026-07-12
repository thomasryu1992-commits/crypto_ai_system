from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.full_regression_ci_release_gate import persist_full_regression_ci_release_gate


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_full_regression_ci_release_gate(cfg=cfg)
    print(report["status"])
    print(report["p18_full_regression_ci_release_gate_sha256"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("live_scaled_execution_enabled=false")
    print("runtime_scheduler_enabled=false")
    return 1 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
