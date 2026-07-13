
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.enablement_pre_submit_review import (
    STEP233_STATUS_OK,
    STEP233_VALIDATION_OK,
    execute_enablement_pre_submit_review,
    validate_enablement_pre_submit_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_enablement_pre_submit_review(root, write_output=True)
    validation = validate_enablement_pre_submit_review(root)
    if result.status != STEP233_STATUS_OK or validation.status != STEP233_VALIDATION_OK:
        print("STEP233_V5_ENABLEMENT_PRE_SUBMIT_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP233_V5_ENABLEMENT_PRE_SUBMIT_REVIEW_ONLY_OK")
    print(f"source_bridge_record_count: {result.source_bridge_record_count}")
    print(f"source_bridge_review_ready_count: {result.source_bridge_review_ready_count}")
    print(f"pre_submit_record_count: {result.pre_submit_record_count}")
    print(f"pre_submit_review_ready_count: {result.pre_submit_review_ready_count}")
    print(f"pre_submit_blocked_count: {result.pre_submit_blocked_count}")
    print(f"enablement_pre_submit_review_created: {result.enablement_pre_submit_review_created}")
    print(f"pre_submit_review_mode: {result.pre_submit_review_mode}")
    print(f"pre_submit_review_only: {result.pre_submit_review_only}")
    print(f"pre_submit_review_passed: {result.pre_submit_review_passed}")
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
