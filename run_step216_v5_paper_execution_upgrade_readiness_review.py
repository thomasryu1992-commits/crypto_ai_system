
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.feedback.paper_execution_upgrade_readiness_review import (
    STEP216_STATUS_OK,
    STEP216_VALIDATION_OK,
    execute_paper_execution_upgrade_readiness_review,
    validate_paper_execution_upgrade_readiness_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_execution_upgrade_readiness_review(root, write_output=True)
    validation = validate_paper_execution_upgrade_readiness_review(root)
    if result.status != STEP216_STATUS_OK or validation.status != STEP216_VALIDATION_OK:
        print("STEP216_V5_PAPER_EXECUTION_UPGRADE_READINESS_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP216_V5_PAPER_EXECUTION_UPGRADE_READINESS_REVIEW_ONLY_OK")
    print(f"source_promotion_decision_count: {result.source_promotion_decision_count}")
    print(f"upgrade_review_count: {result.upgrade_review_count}")
    print(f"upgrade_review_ready_count: {result.upgrade_review_ready_count}")
    print(f"upgrade_watchlist_count: {result.upgrade_watchlist_count}")
    print(f"upgrade_blocked_count: {result.upgrade_blocked_count}")
    print(f"average_upgrade_readiness_score: {result.average_upgrade_readiness_score}")
    print(f"evidence_files_present_count: {result.evidence_files_present_count}")
    print(f"evidence_files_required_count: {result.evidence_files_required_count}")
    print(f"paper_execution_upgrade_readiness_review_created: {result.paper_execution_upgrade_readiness_review_created}")
    print(f"readiness_checklist_applied: {result.readiness_checklist_applied}")
    print(f"operator_review_required: {result.operator_review_required}")
    print(f"manual_approval_required: {result.manual_approval_required}")
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
