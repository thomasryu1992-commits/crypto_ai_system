
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.ops.operator_approval_intake_stub import (
    STEP218_STATUS_OK,
    STEP218_VALIDATION_OK,
    execute_operator_approval_intake_stub,
    validate_operator_approval_intake_stub,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_operator_approval_intake_stub(root, write_output=True)
    validation = validate_operator_approval_intake_stub(root)
    if result.status != STEP218_STATUS_OK or validation.status != STEP218_VALIDATION_OK:
        print("STEP218_V5_OPERATOR_APPROVAL_INTAKE_STUB_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP218_V5_OPERATOR_APPROVAL_INTAKE_STUB_OK")
    print(f"source_approval_packet_count: {result.source_approval_packet_count}")
    print(f"approval_intake_template_count: {result.approval_intake_template_count}")
    print(f"not_approved_template_count: {result.not_approved_template_count}")
    print(f"blocked_template_count: {result.blocked_template_count}")
    print(f"watchlist_template_count: {result.watchlist_template_count}")
    print(f"operator_approval_intake_stub_created: {result.operator_approval_intake_stub_created}")
    print(f"operator_approval_input_schema_created: {result.operator_approval_input_schema_created}")
    print(f"operator_approved: {result.operator_approved}")
    print(f"approval_recorded: {result.approval_recorded}")
    print(f"approval_intake_live: {result.approval_intake_live}")
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
