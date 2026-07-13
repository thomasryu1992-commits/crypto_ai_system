
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.operator_final_approval_intake_validator_review import (
    STEP231_STATUS_OK,
    STEP231_VALIDATION_OK,
    execute_operator_final_approval_intake_validator_review,
    validate_operator_final_approval_intake_validator_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_operator_final_approval_intake_validator_review(root, write_output=True)
    validation = validate_operator_final_approval_intake_validator_review(root)
    if result.status != STEP231_STATUS_OK or validation.status != STEP231_VALIDATION_OK:
        print("STEP231_V5_OPERATOR_FINAL_APPROVAL_INTAKE_VALIDATOR_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP231_V5_OPERATOR_FINAL_APPROVAL_INTAKE_VALIDATOR_REVIEW_ONLY_OK")
    print(f"operator_input_present: {result.operator_input_present}")
    print(f"source_approval_stub_count: {result.source_approval_stub_count}")
    print(f"source_approval_stub_review_ready_count: {result.source_approval_stub_review_ready_count}")
    print(f"intake_record_count: {result.intake_record_count}")
    print(f"intake_valid_count: {result.intake_valid_count}")
    print(f"intake_not_approved_count: {result.intake_not_approved_count}")
    print(f"intake_blocked_count: {result.intake_blocked_count}")
    print(f"operator_final_approval_intake_validator_created: {result.operator_final_approval_intake_validator_created}")
    print(f"intake_validator_mode: {result.intake_validator_mode}")
    print(f"intake_validator_review_only: {result.intake_validator_review_only}")
    print(f"operator_final_approval_input_validated: {result.operator_final_approval_input_validated}")
    print(f"operator_final_approval_accepted: {result.operator_final_approval_accepted}")
    print(f"operator_final_approval_recorded: {result.operator_final_approval_recorded}")
    print(f"operator_final_approval_submitted: {result.operator_final_approval_submitted}")
    print(f"paper_execution_enablement_allowed: {result.paper_execution_enablement_allowed}")
    print(f"paper_execution_enabled: {result.paper_execution_enabled}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
