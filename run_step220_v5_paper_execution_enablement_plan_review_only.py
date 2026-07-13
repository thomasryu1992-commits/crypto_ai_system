
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.paper_execution_enablement_plan_review_only import (
    STEP220_STATUS_OK,
    STEP220_VALIDATION_OK,
    execute_paper_execution_enablement_plan_review_only,
    validate_paper_execution_enablement_plan_review_only,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_execution_enablement_plan_review_only(root, write_output=True)
    validation = validate_paper_execution_enablement_plan_review_only(root)
    if result.status != STEP220_STATUS_OK or validation.status != STEP220_VALIDATION_OK:
        print("STEP220_V5_PAPER_EXECUTION_ENABLEMENT_PLAN_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP220_V5_PAPER_EXECUTION_ENABLEMENT_PLAN_REVIEW_ONLY_OK")
    print(f"source_validation_record_count: {result.source_validation_record_count}")
    print(f"validation_passed_count: {result.validation_passed_count}")
    print(f"enablement_plan_count: {result.enablement_plan_count}")
    print(f"plan_ready_count: {result.plan_ready_count}")
    print(f"plan_blocked_count: {result.plan_blocked_count}")
    print(f"plan_watchlist_count: {result.plan_watchlist_count}")
    print(f"total_planned_max_paper_notional_usd: {result.total_planned_max_paper_notional_usd}")
    print(f"paper_execution_enablement_plan_created: {result.paper_execution_enablement_plan_created}")
    print(f"enablement_plan_review_only: {result.enablement_plan_review_only}")
    print(f"execution_mode: {result.execution_mode}")
    print(f"paper_execution_enablement_allowed: {result.paper_execution_enablement_allowed}")
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
