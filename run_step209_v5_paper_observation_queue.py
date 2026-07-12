
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.backtest.paper_observation_queue import (
    STEP209_STATUS_OK,
    STEP209_VALIDATION_OK,
    execute_paper_observation_queue,
    validate_paper_observation_queue,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_observation_queue(root, write_output=True)
    validation = validate_paper_observation_queue(root)
    if result.status != STEP209_STATUS_OK or validation.status != STEP209_VALIDATION_OK:
        print("STEP209_V5_PAPER_OBSERVATION_QUEUE_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP209_V5_PAPER_OBSERVATION_QUEUE_OK")
    print(f"queue_item_count: {result.queue_item_count}")
    print(f"active_observation_count: {result.active_observation_count}")
    print(f"watchlist_observation_count: {result.watchlist_observation_count}")
    print(f"blocked_observation_count: {result.blocked_observation_count}")
    print(f"paper_observation_queue_created: {result.paper_observation_queue_created}")
    print(f"paper_signal_observation_enabled: {result.paper_signal_observation_enabled}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"source_policy_enforced: {result.source_policy_enforced}")
    print(f"operator_review_required: {result.operator_review_required}")
    print(f"auto_strategy_promotion: {result.auto_strategy_promotion}")
    print(f"external_api_call_performed: {result.external_api_call_performed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
