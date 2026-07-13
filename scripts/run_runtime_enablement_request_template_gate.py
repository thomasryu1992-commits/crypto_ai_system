from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_accepted_release_candidate_handoff import persist_operator_accepted_release_candidate_handoff


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P23 runtime enablement request template gate.")
    parser.add_argument("--print-template", action="store_true", help="Print the generated review-only runtime enablement request template.")
    args = parser.parse_args()
    report = persist_operator_accepted_release_candidate_handoff(load_config(Path.cwd()))
    if args.print_template:
        print(json.dumps(report["runtime_enablement_request_template"], indent=2, sort_keys=True))
        return
    print(report["status"])
    print(report["p23_operator_accepted_release_candidate_handoff_sha256"])
    print(f"limited_live_scaled_auto_trading_allowed={str(report['limited_live_scaled_auto_trading_allowed']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")


if __name__ == "__main__":
    main()
