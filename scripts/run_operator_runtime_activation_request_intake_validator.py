from __future__ import annotations

import argparse
import json

from crypto_ai_system.execution.operator_runtime_activation_request_intake_validator import (
    build_operator_runtime_activation_request_intake_template,
    persist_operator_runtime_activation_request_intake_validator,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate P27 operator runtime activation request intake artifacts.")
    parser.add_argument("--print-template", action="store_true", help="Print the review-only P27 activation request intake template and exit.")
    args = parser.parse_args()
    if args.print_template:
        print(json.dumps(build_operator_runtime_activation_request_intake_template(), indent=2, sort_keys=True))
        return 0
    report = persist_operator_runtime_activation_request_intake_validator()
    print(json.dumps({
        "status": report["status"],
        "p27_operator_runtime_activation_request_intake_valid_review_only": report["p27_operator_runtime_activation_request_intake_valid_review_only"],
        "operator_runtime_activation_request_validated_review_only": report["operator_runtime_activation_request_validated_review_only"],
        "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
        "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
        "secret_value_accessed": report["secret_value_accessed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
