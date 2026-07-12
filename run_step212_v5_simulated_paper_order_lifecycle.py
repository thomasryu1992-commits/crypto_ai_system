
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.execution.simulated_paper_order_lifecycle import (
    STEP212_STATUS_OK,
    STEP212_VALIDATION_OK,
    execute_simulated_paper_order_lifecycle,
    validate_simulated_paper_order_lifecycle,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_simulated_paper_order_lifecycle(root, write_output=True)
    validation = validate_simulated_paper_order_lifecycle(root)
    if result.status != STEP212_STATUS_OK or validation.status != STEP212_VALIDATION_OK:
        print("STEP212_V5_SIMULATED_PAPER_ORDER_LIFECYCLE_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP212_V5_SIMULATED_PAPER_ORDER_LIFECYCLE_OK")
    print(f"source_dry_run_intent_count: {result.source_dry_run_intent_count}")
    print(f"lifecycle_summary_count: {result.lifecycle_summary_count}")
    print(f"lifecycle_event_count: {result.lifecycle_event_count}")
    print(f"simulated_submitted_count: {result.simulated_submitted_count}")
    print(f"simulated_ack_count: {result.simulated_ack_count}")
    print(f"simulated_filled_count: {result.simulated_filled_count}")
    print(f"simulated_closed_count: {result.simulated_closed_count}")
    print(f"simulated_rejected_count: {result.simulated_rejected_count}")
    print(f"paper_order_lifecycle_simulation_enabled: {result.paper_order_lifecycle_simulation_enabled}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"auto_strategy_promotion: {result.auto_strategy_promotion}")
    print(f"external_api_call_performed: {result.external_api_call_performed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
