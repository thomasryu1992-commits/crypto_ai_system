from pathlib import Path

from crypto_ai_system.ops.dry_run_paper_execution_config_review import (
    CONFIG_MODE_DRAFT_ONLY,
    STEP221_STATUS_OK,
    STEP221_VALIDATION_OK,
    execute_dry_run_paper_execution_config_review,
    validate_dry_run_paper_execution_config_review,
)


def test_step221_creates_config_drafts_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_dry_run_paper_execution_config_review(root, write_output=True)
    assert result.status == STEP221_STATUS_OK
    assert result.dry_run_paper_execution_config_review_created is True
    assert result.config_mode == CONFIG_MODE_DRAFT_ONLY
    assert result.config_draft_only is True
    assert result.source_enablement_plan_count > 0
    assert result.config_draft_count > 0


def test_step221_keeps_config_apply_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_dry_run_paper_execution_config_review(root, write_output=True)
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
    for draft in result.drafts:
        assert draft["config_mode"] == CONFIG_MODE_DRAFT_ONLY
        assert draft["config_draft_created"] is True
        assert draft["config_apply_allowed"] is False
        assert draft["config_applied"] is False
        assert draft["paper_execution_enabled"] is False
        assert draft["paper_order_execution_enabled"] is False
        assert draft["adapter_routing_enabled"] is False
        assert draft["shadow_execution_enabled"] is False
        assert draft["limited_live_review_allowed"] is False
        assert draft["live_trading_allowed"] is False
        assert draft["strategy_registry_write_allowed"] is False
        assert draft["promotion_allowed"] is False


def test_step221_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_dry_run_paper_execution_config_review(root, write_output=True)
    validation = validate_dry_run_paper_execution_config_review(root)
    assert validation.status == STEP221_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step220_present is True
    assert validation.config_drafts_json_exists is True
    assert validation.config_drafts_jsonl_exists is True
    assert validation.config_drafts_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_enablement_plans_present is True
    assert validation.config_drafts_present is True
    assert validation.config_review_created is True
    assert validation.config_mode_draft_only is True
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
