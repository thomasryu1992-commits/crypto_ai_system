
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.feedback.promotion_gate_v2_review_only import (
    STEP215_STATUS_OK,
    STEP215_VALIDATION_OK,
    execute_promotion_gate_v2_review_only,
    validate_promotion_gate_v2_review_only,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_promotion_gate_v2_review_only(root, write_output=True)
    validation = validate_promotion_gate_v2_review_only(root)
    if result.status != STEP215_STATUS_OK or validation.status != STEP215_VALIDATION_OK:
        print("STEP215_V5_PROMOTION_GATE_V2_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP215_V5_PROMOTION_GATE_V2_REVIEW_ONLY_OK")
    print(f"source_feedback_review_count: {result.source_feedback_review_count}")
    print(f"promotion_decision_count: {result.promotion_decision_count}")
    print(f"promotion_review_ready_count: {result.promotion_review_ready_count}")
    print(f"promotion_watchlist_count: {result.promotion_watchlist_count}")
    print(f"promotion_blocked_count: {result.promotion_blocked_count}")
    print(f"average_promotion_readiness_score: {result.average_promotion_readiness_score}")
    print(f"promotion_gate_v2_review_only_created: {result.promotion_gate_v2_review_only_created}")
    print(f"promotion_gate_applied: {result.promotion_gate_applied}")
    print(f"promotion_gate_input_ready: {result.promotion_gate_input_ready}")
    print(f"operator_review_required: {result.operator_review_required}")
    print(f"promotion_allowed: {result.promotion_allowed}")
    print(f"auto_strategy_promotion: {result.auto_strategy_promotion}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
    print(f"paper_execution_upgrade_allowed: {result.paper_execution_upgrade_allowed}")
    print(f"limited_live_review_allowed: {result.limited_live_review_allowed}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"external_api_call_performed: {result.external_api_call_performed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
