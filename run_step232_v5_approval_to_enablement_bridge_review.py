
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.approval_to_enablement_bridge_review import (
    STEP232_STATUS_OK,
    STEP232_VALIDATION_OK,
    execute_approval_to_enablement_bridge_review,
    validate_approval_to_enablement_bridge_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_approval_to_enablement_bridge_review(root, write_output=True)
    validation = validate_approval_to_enablement_bridge_review(root)
    if result.status != STEP232_STATUS_OK or validation.status != STEP232_VALIDATION_OK:
        print("STEP232_V5_APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP232_V5_APPROVAL_TO_ENABLEMENT_BRIDGE_REVIEW_ONLY_OK")
    print(f"source_intake_record_count: {result.source_intake_record_count}")
    print(f"source_intake_valid_count: {result.source_intake_valid_count}")
    print(f"bridge_record_count: {result.bridge_record_count}")
    print(f"bridge_review_ready_count: {result.bridge_review_ready_count}")
    print(f"bridge_blocked_count: {result.bridge_blocked_count}")
    print(f"approval_to_enablement_bridge_review_created: {result.approval_to_enablement_bridge_review_created}")
    print(f"bridge_mode: {result.bridge_mode}")
    print(f"bridge_review_only: {result.bridge_review_only}")
    print(f"approval_bridge_passed: {result.approval_bridge_passed}")
    print(f"operator_final_approval_accepted: {result.operator_final_approval_accepted}")
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
