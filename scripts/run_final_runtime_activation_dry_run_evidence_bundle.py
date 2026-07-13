from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_runtime_activation_dry_run_evidence_bundle import persist_final_runtime_activation_dry_run_evidence_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P29 final runtime activation dry-run evidence bundle gate.")
    parser.add_argument("--print-template", action="store_true", help="Print generated P29 dry-run evidence template as JSON.")
    args = parser.parse_args()
    report = persist_final_runtime_activation_dry_run_evidence_bundle(load_config(Path.cwd()))
    if args.print_template:
        print(json.dumps(report["p29_final_runtime_activation_dry_run_evidence_template"], indent=2, sort_keys=True))
        return 0
    print(report["status"])
    print(f"live_scaled_execution_enabled={str(report['live_scaled_execution_enabled']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")
    print(f"live_order_submission_allowed={str(report['live_order_submission_allowed']).lower()}")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
