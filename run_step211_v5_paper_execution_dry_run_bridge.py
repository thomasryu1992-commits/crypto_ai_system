
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.execution.paper_execution_dry_run_bridge import (
    STEP211_STATUS_OK,
    STEP211_VALIDATION_OK,
    execute_paper_execution_dry_run_bridge,
    validate_paper_execution_dry_run_bridge,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_execution_dry_run_bridge(root, write_output=True)
    validation = validate_paper_execution_dry_run_bridge(root)
    if result.status != STEP211_STATUS_OK or validation.status != STEP211_VALIDATION_OK:
        print("STEP211_V5_PAPER_EXECUTION_DRY_RUN_BRIDGE_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP211_V5_PAPER_EXECUTION_DRY_RUN_BRIDGE_OK")
    print(f"source_replay_summary_count: {result.source_replay_summary_count}")
    print(f"source_replay_event_count: {result.source_replay_event_count}")
    print(f"eligible_replay_summary_count: {result.eligible_replay_summary_count}")
    print(f"dry_run_intent_count: {result.dry_run_intent_count}")
    print(f"candidate_summary_count: {result.candidate_summary_count}")
    print(f"paper_execution_dry_run_bridge_created: {result.paper_execution_dry_run_bridge_created}")
    print(f"paper_order_intent_dry_run_created: {result.paper_order_intent_dry_run_created}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"adapter_routing_enabled: {result.adapter_routing_enabled}")
    print(f"shadow_execution_enabled: {result.shadow_execution_enabled}")
    print(f"order_lifecycle_simulation_enabled: {result.order_lifecycle_simulation_enabled}")
    print(f"auto_strategy_promotion: {result.auto_strategy_promotion}")
    print(f"external_api_call_performed: {result.external_api_call_performed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
