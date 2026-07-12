
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.operator_final_enablement_approval_stub_review import (
    STEP230_STATUS_OK,
    STEP230_VALIDATION_OK,
    execute_operator_final_enablement_approval_stub_review,
    validate_operator_final_enablement_approval_stub_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_operator_final_enablement_approval_stub_review(root, write_output=True)
    validation = validate_operator_final_enablement_approval_stub_review(root)
    if result.status != STEP230_STATUS_OK or validation.status != STEP230_VALIDATION_OK:
        print("STEP230_V5_OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP230_V5_OPERATOR_FINAL_ENABLEMENT_APPROVAL_STUB_REVIEW_ONLY_OK")
    print(f"source_final_validation_record_count: {result.source_final_validation_record_count}")
    print(f"source_final_validation_review_ready_count: {result.source_final_validation_review_ready_count}")
    print(f"approval_stub_count: {result.approval_stub_count}")
    print(f"approval_stub_review_ready_count: {result.approval_stub_review_ready_count}")
    print(f"approval_stub_blocked_count: {result.approval_stub_blocked_count}")
    print(f"operator_final_approval_stub_review_created: {result.operator_final_approval_stub_review_created}")
    print(f"approval_stub_mode: {result.approval_stub_mode}")
    print(f"approval_stub_only: {result.approval_stub_only}")
    print(f"operator_final_approval_template_created: {result.operator_final_approval_template_created}")
    print(f"operator_final_approval_submitted: {result.operator_final_approval_submitted}")
    print(f"operator_final_approval_recorded: {result.operator_final_approval_recorded}")
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
