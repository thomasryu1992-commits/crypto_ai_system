from pathlib import Path

from crypto_ai_system.ops.dry_run_config_apply_validator_review_only import (
    STEP222_STATUS_OK,
    STEP222_VALIDATION_OK,
    execute_dry_run_config_apply_validator_review_only,
    validate_dry_run_config_apply_validator_review_only,
)


def test_step222_creates_apply_validation_records_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_dry_run_config_apply_validator_review_only(root, write_output=True)
    assert result.status == STEP222_STATUS_OK
    assert result.dry_run_config_apply_validator_created is True
    assert result.config_apply_validation_performed is True
    assert result.source_config_draft_count > 0
    assert result.apply_validation_record_count > 0


def test_step222_keeps_config_apply_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_dry_run_config_apply_validator_review_only(root, write_output=True)
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
    for record in result.records:
        assert record["config_apply_validation_created"] is True
        assert record["config_apply_allowed"] is False
        assert record["config_applied"] is False
        assert record["paper_execution_enabled"] is False
        assert record["paper_order_execution_enabled"] is False
        assert record["adapter_routing_enabled"] is False
        assert record["shadow_execution_enabled"] is False
        assert record["limited_live_review_allowed"] is False
        assert record["live_trading_allowed"] is False
        assert record["strategy_registry_write_allowed"] is False
        assert record["promotion_allowed"] is False


def test_step222_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_dry_run_config_apply_validator_review_only(root, write_output=True)
    validation = validate_dry_run_config_apply_validator_review_only(root)
    assert validation.status == STEP222_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step221_present is True
    assert validation.apply_validation_records_json_exists is True
    assert validation.apply_validation_records_jsonl_exists is True
    assert validation.apply_validation_records_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_config_drafts_present is True
    assert validation.apply_validation_records_present is True
    assert validation.apply_validator_created is True
    assert validation.validation_performed is True
    assert validation.no_config_apply_allowed is True
    assert validation.no_config_applied is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_enablement_allowed is True
    assert validation.no_paper_execution_upgrade is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_limited_live_review is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_promotion_allowed is True
    assert validation.no_live_side_effects is True
