from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_operator_runtime_activation_gate_review import persist_final_operator_runtime_activation_gate_review


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P28 final operator runtime activation gate review.")
    parser.add_argument("--print-template", action="store_true", help="Print generated P28 controls template as JSON.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_final_operator_runtime_activation_gate_review(cfg)
    if args.print_template:
        print(json.dumps(report["p28_final_operator_runtime_activation_gate_review_controls_template"], indent=2, sort_keys=True))
        return 0
    print(report["status"])
    print(f"live_scaled_execution_enabled={str(report['live_scaled_execution_enabled']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")
    print(f"live_order_submission_allowed={str(report['live_order_submission_allowed']).lower()}")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
