from pathlib import Path

from crypto_ai_system.execution.paper_execution_dry_run_bridge import (
    STEP211_STATUS_OK,
    STEP211_VALIDATION_OK,
    execute_paper_execution_dry_run_bridge,
    validate_paper_execution_dry_run_bridge,
)


def test_step211_creates_dry_run_order_intent_artifacts(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_dry_run_bridge(root, write_output=True)
    assert result.status == STEP211_STATUS_OK
    assert result.paper_execution_dry_run_bridge_created is True
    assert result.paper_order_intent_dry_run_created is True
    assert result.eligible_replay_summary_count > 0
    assert result.dry_run_intent_count > 0
    assert result.candidate_summary_count > 0


def test_step211_keeps_all_execution_boundaries_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_dry_run_bridge(root, write_output=True)
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.order_lifecycle_simulation_enabled is False
    assert result.auto_strategy_promotion is False
    assert result.external_api_call_performed is False
    assert result.live_order_executed is False
    assert result.real_adapter_call_performed is False
    assert result.telegram_real_send is False
    assert result.production_cutover_executable is False
    assert result.live_mode_enable_allowed is False
    for intent in result.sample_dry_run_order_intents:
        assert intent["execution_allowed"] is False
        assert intent["paper_order_created"] is False
        assert intent["paper_order_submitted"] is False
        assert intent["adapter_routing_enabled"] is False
        assert intent["live_order_executed"] is False


def test_step211_validation_artifacts_exist_and_idempotency_is_unique(isolated_project_root):
    root = isolated_project_root
    execute_paper_execution_dry_run_bridge(root, write_output=True)
    validation = validate_paper_execution_dry_run_bridge(root)
    assert validation.status == STEP211_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step210_present is True
    assert validation.dry_run_intents_json_exists is True
    assert validation.dry_run_summary_json_exists is True
    assert validation.dry_run_summary_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.dry_run_intents_present is True
    assert validation.idempotency_keys_unique is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_order_lifecycle_simulation is True
    assert validation.no_live_side_effects is True
