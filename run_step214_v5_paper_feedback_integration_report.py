
from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.feedback.paper_feedback_integration_report import (
    STEP214_STATUS_OK,
    STEP214_VALIDATION_OK,
    execute_paper_feedback_integration_report,
    validate_paper_feedback_integration_report,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    result = execute_paper_feedback_integration_report(root, write_output=True)
    validation = validate_paper_feedback_integration_report(root)
    if result.status != STEP214_STATUS_OK or validation.status != STEP214_VALIDATION_OK:
        print("STEP214_V5_PAPER_FEEDBACK_INTEGRATION_REPORT_FAILED")
        print(validation.to_dict())
        return 1
    print("STEP214_V5_PAPER_FEEDBACK_INTEGRATION_REPORT_OK")
    print(f"source_candidate_aggregate_count: {result.source_candidate_aggregate_count}")
    print(f"feedback_review_count: {result.feedback_review_count}")
    print(f"review_only_candidate_count: {result.review_only_candidate_count}")
    print(f"watchlist_candidate_count: {result.watchlist_candidate_count}")
    print(f"blocked_candidate_count: {result.blocked_candidate_count}")
    print(f"average_feedback_score: {result.average_feedback_score}")
    print(f"max_feedback_score: {result.max_feedback_score}")
    print(f"min_feedback_score: {result.min_feedback_score}")
    print(f"feedback_integration_report_created: {result.feedback_integration_report_created}")
    print(f"feedback_engine_input_ready: {result.feedback_engine_input_ready}")
    print(f"promotion_gate_input_ready: {result.promotion_gate_input_ready}")
    print(f"promotion_allowed: {result.promotion_allowed}")
    print(f"strategy_registry_write_allowed: {result.strategy_registry_write_allowed}")
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
