
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.operator_approval_intake_validator import (
    STEP219_STATUS_OK,
    STEP219_VALIDATION_OK,
    execute_operator_approval_intake_validator,
    validate_operator_approval_intake_validator,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_operator_approval_intake_validator(root, write_output=True)
    validation = validate_operator_approval_intake_validator(root)
    if result.status != STEP219_STATUS_OK or validation.status != STEP219_VALIDATION_OK:
        print("STEP219_V5_OPERATOR_APPROVAL_INTAKE_VALIDATOR_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP219_V5_OPERATOR_APPROVAL_INTAKE_VALIDATOR_OK")
    print(f"source_intake_template_count: {result.source_intake_template_count}")
    print(f"operator_input_present: {result.operator_input_present}")
    print(f"validation_record_count: {result.validation_record_count}")
    print(f"validation_passed_count: {result.validation_passed_count}")
    print(f"validation_failed_count: {result.validation_failed_count}")
    print(f"validation_not_approved_count: {result.validation_not_approved_count}")
    print(f"operator_approval_intake_validator_created: {result.operator_approval_intake_validator_created}")
    print(f"approval_validation_performed: {result.approval_validation_performed}")
    print(f"validated_operator_approval_present: {result.validated_operator_approval_present}")
    print(f"operator_approved: {result.operator_approved}")
    print(f"approval_recorded: {result.approval_recorded}")
    print(f"approval_intake_live: {result.approval_intake_live}")
    print(f"paper_execution_upgrade_allowed: {result.paper_execution_upgrade_allowed}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"limited_live_review_allowed: {result.limited_live_review_allowed}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
    print(f"promotion_allowed: {result.promotion_allowed}")
    print(f"auto_strategy_promotion: {result.auto_strategy_promotion}")
    print(f"external_api_call_performed: {result.external_api_call_performed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
