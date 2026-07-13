from pathlib import Path

from crypto_ai_system.ops.operator_approval_intake_stub import (
    STEP218_STATUS_OK,
    STEP218_VALIDATION_OK,
    execute_operator_approval_intake_stub,
    validate_operator_approval_intake_stub,
)


def test_step218_creates_operator_approval_intake_templates(isolated_project_root):
    root = isolated_project_root
    result = execute_operator_approval_intake_stub(root, write_output=True)
    assert result.status == STEP218_STATUS_OK
    assert result.operator_approval_intake_stub_created is True
    assert result.operator_approval_input_schema_created is True
    assert result.source_approval_packet_count > 0
    assert result.approval_intake_template_count > 0
    assert result.not_approved_template_count == result.approval_intake_template_count


def test_step218_defaults_everything_to_not_approved_and_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_operator_approval_intake_stub(root, write_output=True)
    assert result.operator_approved is False
    assert result.approval_recorded is False
    assert result.approval_intake_live is False
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
    for template in result.templates:
        assert template["operator_approved"] is False
        assert template["approval_recorded"] is False
        assert template["approved_by"] == ""
        assert template["approval_time_utc"] == ""
        assert template["approval_reason"] == ""
        assert template["approval_decision"] == "NOT_APPROVED"
        assert template["max_paper_notional_usd"] == 0.0
        assert template["max_daily_paper_loss_usd"] == 0.0
        assert template["max_paper_positions"] == 0
        assert template["paper_execution_upgrade_allowed"] is False
        assert template["paper_order_execution_enabled"] is False
        assert template["adapter_routing_enabled"] is False
        assert template["limited_live_review_allowed"] is False
        assert template["live_trading_allowed"] is False


def test_step218_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_operator_approval_intake_stub(root, write_output=True)
    validation = validate_operator_approval_intake_stub(root)
    assert validation.status == STEP218_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step217_present is True
    assert validation.approval_intake_templates_json_exists is True
    assert validation.approval_intake_templates_jsonl_exists is True
    assert validation.approval_intake_templates_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_approval_packets_present is True
    assert validation.approval_intake_templates_present is True
    assert validation.intake_stub_created is True
    assert validation.input_schema_created is True
    assert validation.all_templates_not_approved is True
    assert validation.no_operator_approval_recorded is True
    assert validation.no_live_approval_intake is True
    assert validation.no_paper_execution_upgrade is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_limited_live_review is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_promotion_allowed is True
    assert validation.no_live_side_effects is True
