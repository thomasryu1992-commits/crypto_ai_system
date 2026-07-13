
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.dry_run_config_apply_validator_review_only import (
    STEP222_STATUS_OK,
    STEP222_VALIDATION_OK,
    execute_dry_run_config_apply_validator_review_only,
    validate_dry_run_config_apply_validator_review_only,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_dry_run_config_apply_validator_review_only(root, write_output=True)
    validation = validate_dry_run_config_apply_validator_review_only(root)
    if result.status != STEP222_STATUS_OK or validation.status != STEP222_VALIDATION_OK:
        print("STEP222_V5_DRY_RUN_CONFIG_APPLY_VALIDATOR_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP222_V5_DRY_RUN_CONFIG_APPLY_VALIDATOR_REVIEW_ONLY_OK")
    print(f"source_config_draft_count: {result.source_config_draft_count}")
    print(f"source_config_review_ready_count: {result.source_config_review_ready_count}")
    print(f"apply_validation_record_count: {result.apply_validation_record_count}")
    print(f"apply_validation_passed_count: {result.apply_validation_passed_count}")
    print(f"apply_validation_blocked_count: {result.apply_validation_blocked_count}")
    print(f"apply_validation_watchlist_count: {result.apply_validation_watchlist_count}")
    print(f"dry_run_config_apply_validator_created: {result.dry_run_config_apply_validator_created}")
    print(f"config_apply_validation_performed: {result.config_apply_validation_performed}")
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
