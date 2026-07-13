
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.feedback.paper_lifecycle_outcome_store import (
    STEP213_STATUS_OK,
    STEP213_VALIDATION_OK,
    execute_paper_lifecycle_outcome_store,
    validate_paper_lifecycle_outcome_store,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_lifecycle_outcome_store(root, write_output=True)
    validation = validate_paper_lifecycle_outcome_store(root)
    if result.status != STEP213_STATUS_OK or validation.status != STEP213_VALIDATION_OK:
        print("STEP213_V5_PAPER_LIFECYCLE_OUTCOME_STORE_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP213_V5_PAPER_LIFECYCLE_OUTCOME_STORE_OK")
    print(f"source_lifecycle_summary_count: {result.source_lifecycle_summary_count}")
    print(f"outcome_record_count: {result.outcome_record_count}")
    print(f"candidate_aggregate_count: {result.candidate_aggregate_count}")
    print(f"feedback_ready_candidate_count: {result.feedback_ready_candidate_count}")
    print(f"watchlist_candidate_count: {result.watchlist_candidate_count}")
    print(f"blocked_candidate_count: {result.blocked_candidate_count}")
    print(f"outcome_store_created: {result.outcome_store_created}")
    print(f"outcome_evidence_store_enabled: {result.outcome_evidence_store_enabled}")
    print(f"feedback_engine_input_ready: {result.feedback_engine_input_ready}")
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
