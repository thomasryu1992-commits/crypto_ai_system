
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.enablement_submit_decision_intake_validator_review import (
    STEP235_STATUS_OK,
    STEP235_VALIDATION_OK,
    execute_enablement_submit_decision_intake_validator_review,
    validate_enablement_submit_decision_intake_validator_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_enablement_submit_decision_intake_validator_review(root, write_output=True)
    validation = validate_enablement_submit_decision_intake_validator_review(root)
    if result.status != STEP235_STATUS_OK or validation.status != STEP235_VALIDATION_OK:
        print("STEP235_V5_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP235_V5_ENABLEMENT_SUBMIT_DECISION_INTAKE_VALIDATOR_REVIEW_ONLY_OK")
    print(f"submit_decision_input_present: {result.submit_decision_input_present}")
    print(f"source_submit_decision_count: {result.source_submit_decision_count}")
    print(f"source_submit_decision_review_ready_count: {result.source_submit_decision_review_ready_count}")
    print(f"intake_record_count: {result.intake_record_count}")
    print(f"intake_valid_count: {result.intake_valid_count}")
    print(f"intake_not_approved_count: {result.intake_not_approved_count}")
    print(f"intake_blocked_count: {result.intake_blocked_count}")
    print(f"submit_decision_intake_validator_created: {result.submit_decision_intake_validator_created}")
    print(f"intake_validator_mode: {result.intake_validator_mode}")
    print(f"intake_validator_review_only: {result.intake_validator_review_only}")
    print(f"submit_decision_input_validated: {result.submit_decision_input_validated}")
    print(f"submit_decision_accepted: {result.submit_decision_accepted}")
    print(f"submit_decision_recorded: {result.submit_decision_recorded}")
    print(f"submit_decision_approved: {result.submit_decision_approved}")
    print(f"enablement_request_submit_allowed: {result.enablement_request_submit_allowed}")
    print(f"enablement_request_submitted: {result.enablement_request_submitted}")
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
