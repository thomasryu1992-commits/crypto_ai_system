
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.config_activation_apply_stub_review_only import (
    STEP224_STATUS_OK,
    STEP224_VALIDATION_OK,
    execute_config_activation_apply_stub_review_only,
    validate_config_activation_apply_stub_review_only,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_config_activation_apply_stub_review_only(root, write_output=True)
    validation = validate_config_activation_apply_stub_review_only(root)
    if result.status != STEP224_STATUS_OK or validation.status != STEP224_VALIDATION_OK:
        print("STEP224_V5_CONFIG_ACTIVATION_APPLY_STUB_REVIEW_ONLY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP224_V5_CONFIG_ACTIVATION_APPLY_STUB_REVIEW_ONLY_OK")
    print(f"source_activation_candidate_count: {result.source_activation_candidate_count}")
    print(f"apply_stub_count: {result.apply_stub_count}")
    print(f"apply_stub_review_ready_count: {result.apply_stub_review_ready_count}")
    print(f"apply_stub_blocked_count: {result.apply_stub_blocked_count}")
    print(f"config_activation_apply_stub_review_created: {result.config_activation_apply_stub_review_created}")
    print(f"apply_mode: {result.apply_mode}")
    print(f"apply_stub_only: {result.apply_stub_only}")
    print(f"apply_request_submitted: {result.apply_request_submitted}")
    print(f"config_activation_allowed: {result.config_activation_allowed}")
    print(f"config_activated: {result.config_activated}")
    print(f"config_apply_allowed: {result.config_apply_allowed}")
    print(f"config_applied: {result.config_applied}")
    print(f"paper_execution_enabled: {result.paper_execution_enabled}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"live_trading_allowed: {result.live_trading_allowed}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
    print(f"promotion_allowed: {result.promotion_allowed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
