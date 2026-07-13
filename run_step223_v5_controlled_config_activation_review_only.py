
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.controlled_config_activation_review_only import (
    STEP223_STATUS_OK,
    STEP223_VALIDATION_OK,
    execute_controlled_config_activation_review_only,
    validate_controlled_config_activation_review_only,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_controlled_config_activation_review_only(root, write_output=True)
    validation = validate_controlled_config_activation_review_only(root)
    if result.status != STEP223_STATUS_OK or validation.status != STEP223_VALIDATION_OK:
        print("STEP223_V5_CONTROLLED_CONFIG_ACTIVATION_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP223_V5_CONTROLLED_CONFIG_ACTIVATION_REVIEW_ONLY_OK")
    print(f"source_apply_validation_record_count: {result.source_apply_validation_record_count}")
    print(f"source_apply_validation_passed_count: {result.source_apply_validation_passed_count}")
    print(f"activation_candidate_count: {result.activation_candidate_count}")
    print(f"activation_review_ready_count: {result.activation_review_ready_count}")
    print(f"activation_blocked_count: {result.activation_blocked_count}")
    print(f"activation_watchlist_count: {result.activation_watchlist_count}")
    print(f"controlled_config_activation_review_created: {result.controlled_config_activation_review_created}")
    print(f"activation_mode: {result.activation_mode}")
    print(f"activation_review_only: {result.activation_review_only}")
    print(f"config_activation_allowed: {result.config_activation_allowed}")
    print(f"config_activated: {result.config_activated}")
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
