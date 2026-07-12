from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_activation_readiness_go_no_go_matrix import persist_final_activation_readiness_go_no_go_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P30 final activation readiness Go/No-Go matrix generator.")
    parser.add_argument("--print-matrix", action="store_true", help="Print generated P30 Go/No-Go matrix as JSON.")
    args = parser.parse_args()
    report = persist_final_activation_readiness_go_no_go_matrix(load_config(Path.cwd()))
    if args.print_matrix:
        print(json.dumps(report["go_no_go_matrix"], indent=2, sort_keys=True))
        return 0
    print(report["status"])
    print(f"operator_final_activation_decision={report['operator_final_activation_decision']}")
    print(f"live_scaled_execution_enabled={str(report['live_scaled_execution_enabled']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")
    print(f"live_order_submission_allowed={str(report['live_order_submission_allowed']).lower()}")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
