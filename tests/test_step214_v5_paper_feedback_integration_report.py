from pathlib import Path

from crypto_ai_system.feedback.paper_feedback_integration_report import (
    STEP214_STATUS_OK,
    STEP214_VALIDATION_OK,
    execute_paper_feedback_integration_report,
    validate_paper_feedback_integration_report,
)


def test_step214_creates_feedback_reviews_and_report(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_feedback_integration_report(root, write_output=True, allow_source_regeneration=True)
    assert result.status == STEP214_STATUS_OK
    assert result.feedback_integration_report_created is True
    assert result.feedback_engine_input_ready is True
    assert result.promotion_gate_input_ready is True
    assert result.source_candidate_aggregate_count > 0
    assert result.feedback_review_count > 0
    assert result.average_feedback_score >= 0.0
    assert result.max_feedback_score >= result.min_feedback_score


def test_step214_keeps_promotion_and_execution_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_feedback_integration_report(root, write_output=True, allow_source_regeneration=True)
    assert result.promotion_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.auto_strategy_promotion is False
    assert result.external_api_call_performed is False
    assert result.live_order_executed is False
    assert result.real_adapter_call_performed is False
    assert result.telegram_real_send is False
    assert result.production_cutover_executable is False
    assert result.live_mode_enable_allowed is False
    for review in result.reviews:
        assert review["promotion_allowed"] is False
        assert review["strategy_registry_write_allowed"] is False
        assert review["paper_order_execution_enabled"] is False
        assert review["live_trading_allowed"] is False


def test_step214_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_feedback_integration_report(root, write_output=True, allow_source_regeneration=True)
    validation = validate_paper_feedback_integration_report(root)
    assert validation.status == STEP214_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step213_present is True
    assert validation.feedback_reviews_json_exists is True
    assert validation.feedback_reviews_jsonl_exists is True
    assert validation.feedback_reviews_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_candidate_aggregates_present is True
    assert validation.feedback_reviews_present is True
    assert validation.feedback_report_created is True
    assert validation.feedback_engine_input_ready is True
    assert validation.promotion_gate_input_ready is True
    assert validation.no_promotion is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_side_effects is True
