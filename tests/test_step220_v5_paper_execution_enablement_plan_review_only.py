from pathlib import Path

from crypto_ai_system.ops.paper_execution_enablement_plan_review_only import (
    STEP220_STATUS_OK,
    STEP220_VALIDATION_OK,
    execute_paper_execution_enablement_plan_review_only,
    validate_paper_execution_enablement_plan_review_only,
)


def test_step220_creates_enablement_plans_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_enablement_plan_review_only(root, write_output=True)
    assert result.status == STEP220_STATUS_OK
    assert result.paper_execution_enablement_plan_created is True
    assert result.enablement_plan_review_only is True
    assert result.execution_mode == "PLAN_ONLY"
    assert result.source_validation_record_count > 0
    assert result.enablement_plan_count > 0


def test_step220_keeps_enablement_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_enablement_plan_review_only(root, write_output=True)
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
    for plan in result.plans:
        assert plan["execution_mode"] == "PLAN_ONLY"
        assert plan["paper_execution_enablement_plan_created"] is True
        assert plan["paper_execution_enablement_allowed"] is False
        assert plan["paper_execution_upgrade_allowed"] is False
        assert plan["paper_order_execution_enabled"] is False
        assert plan["adapter_routing_enabled"] is False
        assert plan["shadow_execution_enabled"] is False
        assert plan["limited_live_review_allowed"] is False
        assert plan["live_trading_allowed"] is False
        assert plan["strategy_registry_write_allowed"] is False
        assert plan["promotion_allowed"] is False


def test_step220_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_execution_enablement_plan_review_only(root, write_output=True)
    validation = validate_paper_execution_enablement_plan_review_only(root)
    assert validation.status == STEP220_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step219_present is True
    assert validation.enablement_plans_json_exists is True
    assert validation.enablement_plans_jsonl_exists is True
    assert validation.enablement_plans_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_validation_records_present is True
    assert validation.enablement_plans_present is True
    assert validation.enablement_plan_created is True
    assert validation.review_only_mode is True
    assert validation.execution_mode_plan_only is True
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
