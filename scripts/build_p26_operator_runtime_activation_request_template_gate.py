from __future__ import annotations

import json

from crypto_ai_system.execution.operator_runtime_activation_request_template_gate import persist_operator_runtime_activation_request_template_gate


def main() -> int:
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
