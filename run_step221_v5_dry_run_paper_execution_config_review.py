
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.dry_run_paper_execution_config_review import (
    STEP221_STATUS_OK,
    STEP221_VALIDATION_OK,
    execute_dry_run_paper_execution_config_review,
    validate_dry_run_paper_execution_config_review,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_dry_run_paper_execution_config_review(root, write_output=True)
    validation = validate_dry_run_paper_execution_config_review(root)
    if result.status != STEP221_STATUS_OK or validation.status != STEP221_VALIDATION_OK:
        print("STEP221_V5_DRY_RUN_PAPER_EXECUTION_CONFIG_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP221_V5_DRY_RUN_PAPER_EXECUTION_CONFIG_REVIEW_ONLY_OK")
    print(f"source_enablement_plan_count: {result.source_enablement_plan_count}")
    print(f"source_plan_ready_count: {result.source_plan_ready_count}")
    print(f"config_draft_count: {result.config_draft_count}")
    print(f"config_review_ready_count: {result.config_review_ready_count}")
    print(f"config_watchlist_count: {result.config_watchlist_count}")
    print(f"config_blocked_count: {result.config_blocked_count}")
    print(f"dry_run_paper_execution_config_review_created: {result.dry_run_paper_execution_config_review_created}")
    print(f"config_mode: {result.config_mode}")
    print(f"config_draft_only: {result.config_draft_only}")
    print(f"config_apply_allowed: {result.config_apply_allowed}")
    print(f"config_applied: {result.config_applied}")
    print(f"paper_execution_enabled: {result.paper_execution_enabled}")
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
