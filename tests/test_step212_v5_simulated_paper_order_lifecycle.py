from pathlib import Path

from crypto_ai_system.execution.simulated_paper_order_lifecycle import (
    STEP212_STATUS_OK,
    STEP212_VALIDATION_OK,
    execute_simulated_paper_order_lifecycle,
    validate_simulated_paper_order_lifecycle,
)


def test_step212_creates_simulated_lifecycle_events(isolated_project_root):
    root = isolated_project_root
    result = execute_simulated_paper_order_lifecycle(root, write_output=True)
    assert result.status == STEP212_STATUS_OK
    assert result.simulated_paper_order_lifecycle_created is True
    assert result.paper_order_lifecycle_simulation_enabled is True
    assert result.source_dry_run_intent_count > 0
    assert result.lifecycle_summary_count > 0
    assert result.lifecycle_event_count > 0
    assert result.simulated_submitted_count > 0
    assert result.simulated_ack_count > 0
    assert result.simulated_filled_count > 0
    assert result.simulated_closed_count > 0


def test_step212_keeps_adapter_and_live_boundaries_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_simulated_paper_order_lifecycle(root, write_output=True)
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
    for event in result.sample_lifecycle_events:
        assert event["adapter_called"] is False
        assert event["paper_order_submitted"] is False
        assert event["live_order_executed"] is False


def test_step212_validation_artifacts_and_sequence_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_simulated_paper_order_lifecycle(root, write_output=True)
    validation = validate_simulated_paper_order_lifecycle(root)
    assert validation.status == STEP212_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step211_present is True
    assert validation.lifecycle_events_json_exists is True
    assert validation.lifecycle_events_jsonl_exists is True
    assert validation.lifecycle_summary_json_exists is True
    assert validation.lifecycle_summary_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_dry_run_intents_present is True
    assert validation.lifecycle_events_present is True
    assert validation.lifecycle_summaries_present is True
    assert validation.lifecycle_simulation_enabled is True
    assert validation.event_sequence_valid is True
    assert validation.no_duplicate_simulated_order_ids is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_side_effects is True
