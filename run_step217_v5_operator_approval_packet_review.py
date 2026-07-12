
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.operator_approval_packet_review import (
    STEP217_STATUS_OK,
    STEP217_VALIDATION_OK,
    execute_operator_approval_packet_review,
    validate_operator_approval_packet_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_operator_approval_packet_review(root, write_output=True)
    validation = validate_operator_approval_packet_review(root)
    if result.status != STEP217_STATUS_OK or validation.status != STEP217_VALIDATION_OK:
        print("STEP217_V5_OPERATOR_APPROVAL_PACKET_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP217_V5_OPERATOR_APPROVAL_PACKET_REVIEW_ONLY_OK")
    print(f"source_upgrade_review_count: {result.source_upgrade_review_count}")
    print(f"approval_packet_count: {result.approval_packet_count}")
    print(f"review_ready_packet_count: {result.review_ready_packet_count}")
    print(f"watchlist_packet_count: {result.watchlist_packet_count}")
    print(f"blocked_packet_count: {result.blocked_packet_count}")
    print(f"operator_approval_packet_created: {result.operator_approval_packet_created}")
    print(f"operator_packet_review_only: {result.operator_packet_review_only}")
    print(f"manual_approval_required: {result.manual_approval_required}")
    print(f"operator_review_required: {result.operator_review_required}")
    print(f"operator_approved: {result.operator_approved}")
    print(f"approval_recorded: {result.approval_recorded}")
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
