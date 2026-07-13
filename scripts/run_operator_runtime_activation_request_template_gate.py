from __future__ import annotations

import argparse
import json

from crypto_ai_system.execution.operator_runtime_activation_request_template_gate import (
    build_final_activation_gate_skeleton,
    build_operator_runtime_activation_request_template,
    persist_operator_runtime_activation_request_template_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the P26 operator runtime activation request template gate artifacts.")
    parser.add_argument("--print-template", action="store_true", help="Print the review-only activation request template and exit.")
    parser.add_argument("--print-skeleton", action="store_true", help="Print the review-only final activation gate skeleton and exit.")
    args = parser.parse_args()
    if args.print_template:
        print(json.dumps(build_operator_runtime_activation_request_template(), indent=2, sort_keys=True))
        return 0
    if args.print_skeleton:
        print(json.dumps(build_final_activation_gate_skeleton(), indent=2, sort_keys=True))
        return 0
    report = persist_operator_runtime_activation_request_template_gate()
    print(json.dumps({
        "status": report["status"],
        "p26_operator_runtime_activation_request_template_generated_review_only": report["p26_operator_runtime_activation_request_template_generated_review_only"],
        "p26_final_activation_gate_skeleton_generated_review_only": report["p26_final_activation_gate_skeleton_generated_review_only"],
        "limited_live_scaled_auto_trading_allowed": report["limited_live_scaled_auto_trading_allowed"],
        "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
        "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
        "secret_value_accessed": report["secret_value_accessed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
