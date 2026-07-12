from __future__ import annotations

import argparse
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.full_regression_ci_release_gate import (
    STATUS_BLOCKED_FAIL_CLOSED,
    build_p18_command_plan,
    persist_full_regression_ci_release_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the P18 CI release gate report without enabling runtime execution.")
    parser.add_argument("--list-commands", action="store_true", help="Print the configured CI command plan after the report status.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_full_regression_ci_release_gate(cfg=cfg)
    print(report["status"])
    print(report["p18_full_regression_ci_release_gate_sha256"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("live_scaled_execution_enabled=false")
    print("live_order_submission_allowed=false")
    print("runtime_scheduler_enabled=false")
    if args.list_commands:
        for item in build_p18_command_plan():
            print(f"{item['command_id']}: {item['command']}")
    return 1 if report["status"] == STATUS_BLOCKED_FAIL_CLOSED else 0


if __name__ == "__main__":
    raise SystemExit(main())
