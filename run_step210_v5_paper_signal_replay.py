
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.backtest.paper_signal_replay import (
    STEP210_STATUS_OK,
    STEP210_VALIDATION_OK,
    execute_paper_signal_replay,
    validate_paper_signal_replay,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_signal_replay(root, write_output=True)
    validation = validate_paper_signal_replay(root)
    if result.status != STEP210_STATUS_OK or validation.status != STEP210_VALIDATION_OK:
        print("STEP210_V5_PAPER_SIGNAL_REPLAY_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP210_V5_PAPER_SIGNAL_REPLAY_OK")
    print(f"queue_item_count: {result.queue_item_count}")
    print(f"eligible_queue_item_count: {result.eligible_queue_item_count}")
    print(f"replay_event_count: {result.replay_event_count}")
    print(f"replay_summary_count: {result.replay_summary_count}")
    print(f"review_summary_count: {result.review_summary_count}")
    print(f"watchlist_summary_count: {result.watchlist_summary_count}")
    print(f"blocked_summary_count: {result.blocked_summary_count}")
    print(f"paper_signal_replay_performed: {result.paper_signal_replay_performed}")
    print(f"paper_order_execution_enabled: {result.paper_order_execution_enabled}")
    print(f"paper_trade_execution_enabled: {result.paper_trade_execution_enabled}")
    print(f"auto_strategy_promotion: {result.auto_strategy_promotion}")
    print(f"external_api_call_performed: {result.external_api_call_performed}")
    print(f"live_order_executed: {result.live_order_executed}")
    print(f"telegram_real_send: {result.telegram_real_send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
