
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.final_config_apply_gate_review_only import STEP225_STATUS_OK, STEP225_VALIDATION_OK, execute_final_config_apply_gate_review_only, validate_final_config_apply_gate_review_only


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_final_config_apply_gate_review_only(root, write_output=True)
    validation = validate_final_config_apply_gate_review_only(root)
    if result.status != STEP225_STATUS_OK or validation.status != STEP225_VALIDATION_OK:
        print("STEP225_V5_FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP225_V5_FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY_OK")
    for key in ["source_apply_stub_count", "final_gate_decision_count", "final_gate_review_ready_count", "final_gate_blocked_count", "final_config_apply_gate_review_created", "final_gate_mode", "final_gate_review_only", "final_apply_gate_passed", "config_apply_allowed", "config_applied", "paper_execution_enabled", "paper_order_execution_enabled", "adapter_routing_enabled", "live_trading_allowed", "strategy_registry_write_allowed", "live_order_executed", "telegram_real_send"]:
        print(f"{key}: {getattr(result, key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
