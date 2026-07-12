from pathlib import Path

from crypto_ai_system.ops.controlled_config_activation_review_only import (
    ACTIVATION_MODE_REVIEW_ONLY,
    STEP223_STATUS_OK,
    STEP223_VALIDATION_OK,
    execute_controlled_config_activation_review_only,
    validate_controlled_config_activation_review_only,
)


def test_step223_creates_activation_candidates_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_controlled_config_activation_review_only(root, write_output=True)
    assert result.status == STEP223_STATUS_OK
    assert result.controlled_config_activation_review_created is True
    assert result.activation_mode == ACTIVATION_MODE_REVIEW_ONLY
    assert result.activation_review_only is True
    assert result.source_apply_validation_record_count > 0
    assert result.activation_candidate_count > 0


def test_step223_keeps_activation_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_controlled_config_activation_review_only(root, write_output=True)
    assert result.config_activation_allowed is False
    assert result.config_activated is False
    assert result.config_apply_allowed is False
    assert result.config_applied is False
    assert result.paper_execution_enabled is False
    assert result.paper_execution_enablement_allowed is False
    assert result.paper_execution_upgrade_allowed is False
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.limited_live_review_allowed is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.promotion_allowed is False
    assert result.auto_strategy_promotion is False
    assert result.external_api_call_performed is False
    assert result.live_order_executed is False
    assert result.real_adapter_call_performed is False
    assert result.telegram_real_send is False
    assert result.production_cutover_executable is False
    assert result.live_mode_enable_allowed is False
    for candidate in result.candidates:
        assert candidate["activation_mode"] == ACTIVATION_MODE_REVIEW_ONLY
        assert candidate["controlled_activation_candidate_created"] is True
        assert candidate["config_activation_allowed"] is False
        assert candidate["config_activated"] is False
        assert candidate["config_apply_allowed"] is False
        assert candidate["paper_execution_enabled"] is False
        assert candidate["paper_order_execution_enabled"] is False
        assert candidate["adapter_routing_enabled"] is False
        assert candidate["limited_live_review_allowed"] is False
        assert candidate["live_trading_allowed"] is False


def test_step223_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_controlled_config_activation_review_only(root, write_output=True)
    validation = validate_controlled_config_activation_review_only(root)
    assert validation.status == STEP223_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step222_present is True
    assert validation.activation_candidates_json_exists is True
    assert validation.activation_candidates_jsonl_exists is True
    assert validation.activation_candidates_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_apply_validation_records_present is True
    assert validation.activation_candidates_present is True
    assert validation.activation_review_created is True
    assert validation.activation_mode_review_only is True
    assert validation.no_config_activation_allowed is True
    assert validation.no_config_activated is True
    assert validation.no_config_apply_allowed is True
    assert validation.no_config_applied is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_enablement_allowed is True
    assert validation.no_paper_execution_upgrade is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_live_side_effects is True
