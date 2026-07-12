
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.paper_execution_mode_pre_enablement_audit_review import (
    STEP227_STATUS_OK,
    STEP227_VALIDATION_OK,
    execute_paper_execution_mode_pre_enablement_audit_review,
    validate_paper_execution_mode_pre_enablement_audit_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_execution_mode_pre_enablement_audit_review(root, write_output=True)
    validation = validate_paper_execution_mode_pre_enablement_audit_review(root)
    if result.status != STEP227_STATUS_OK or validation.status != STEP227_VALIDATION_OK:
        print("STEP227_V5_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP227_V5_PAPER_EXECUTION_MODE_PRE_ENABLEMENT_AUDIT_REVIEW_ONLY_OK")
    print(f"source_shadow_ready_decision_count: {result.source_shadow_ready_decision_count}")
    print(f"source_shadow_ready_review_ready_count: {result.source_shadow_ready_review_ready_count}")
    print(f"audit_record_count: {result.audit_record_count}")
    print(f"audit_review_ready_count: {result.audit_review_ready_count}")
    print(f"audit_blocked_count: {result.audit_blocked_count}")
    print(f"pre_enablement_audit_review_created: {result.pre_enablement_audit_review_created}")
    print(f"audit_mode: {result.audit_mode}")
    print(f"audit_review_only: {result.audit_review_only}")
    print(f"pre_enablement_audit_passed: {result.pre_enablement_audit_passed}")
    print(f"paper_execution_enablement_allowed: {result.paper_execution_enablement_allowed}")
    print(f"paper_execution_enabled: {result.paper_execution_enabled}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
