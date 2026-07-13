from pathlib import Path

from crypto_ai_system.feedback.paper_lifecycle_outcome_store import (
    STEP213_STATUS_OK,
    STEP213_VALIDATION_OK,
    execute_paper_lifecycle_outcome_store,
    validate_paper_lifecycle_outcome_store,
)


def test_step213_creates_outcome_store_and_aggregates(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_lifecycle_outcome_store(root, write_output=True, allow_source_regeneration=True)
    assert result.status == STEP213_STATUS_OK
    assert result.outcome_store_created is True
    assert result.outcome_evidence_store_enabled is True
    assert result.feedback_engine_input_ready is True
    assert result.source_lifecycle_summary_count > 0
    assert result.outcome_record_count > 0
    assert result.candidate_aggregate_count > 0


def test_step213_keeps_execution_and_live_boundaries_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_lifecycle_outcome_store(root, write_output=True, allow_source_regeneration=True)
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
    for record in result.sample_outcome_records:
        assert record["paper_order_submitted"] is False
        assert record["paper_order_execution_enabled"] is False
        assert record["adapter_called"] is False
        assert record["live_order_executed"] is False
    for aggregate in result.aggregates:
        assert aggregate["promotion_allowed"] is False
        assert aggregate["paper_order_execution_enabled"] is False
        assert aggregate["live_trading_allowed"] is False


def test_step213_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_lifecycle_outcome_store(root, write_output=True, allow_source_regeneration=True)
    validation = validate_paper_lifecycle_outcome_store(root)
    assert validation.status == STEP213_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step212_present is True
    assert validation.outcome_records_json_exists is True
    assert validation.outcome_records_jsonl_exists is True
    assert validation.candidate_aggregate_json_exists is True
    assert validation.candidate_aggregate_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_lifecycle_summaries_present is True
    assert validation.outcome_records_present is True
    assert validation.candidate_aggregates_present is True
    assert validation.outcome_store_created is True
    assert validation.feedback_input_ready is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_auto_promotion is True
    assert validation.no_live_side_effects is True
