
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.enablement_submit_decision_stub_review import (
    STEP234_STATUS_OK,
    STEP234_VALIDATION_OK,
    execute_enablement_submit_decision_stub_review,
    validate_enablement_submit_decision_stub_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_enablement_submit_decision_stub_review(root, write_output=True)
    validation = validate_enablement_submit_decision_stub_review(root)
    if result.status != STEP234_STATUS_OK or validation.status != STEP234_VALIDATION_OK:
        print("STEP234_V5_ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP234_V5_ENABLEMENT_SUBMIT_DECISION_STUB_REVIEW_ONLY_OK")
    print(f"source_pre_submit_record_count: {result.source_pre_submit_record_count}")
    print(f"source_pre_submit_review_ready_count: {result.source_pre_submit_review_ready_count}")
    print(f"submit_decision_count: {result.submit_decision_count}")
    print(f"submit_decision_review_ready_count: {result.submit_decision_review_ready_count}")
    print(f"submit_decision_blocked_count: {result.submit_decision_blocked_count}")
    print(f"enablement_submit_decision_stub_created: {result.enablement_submit_decision_stub_created}")
    print(f"submit_decision_mode: {result.submit_decision_mode}")
    print(f"submit_decision_stub_only: {result.submit_decision_stub_only}")
    print(f"submit_decision_template_created: {result.submit_decision_template_created}")
    print(f"submit_decision_approved: {result.submit_decision_approved}")
    print(f"submit_decision_recorded: {result.submit_decision_recorded}")
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
