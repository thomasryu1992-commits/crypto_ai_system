from pathlib import Path

from crypto_ai_system.ops.operator_approval_intake_validator import (
    STEP219_STATUS_OK,
    STEP219_VALIDATION_OK,
    execute_operator_approval_intake_validator,
    validate_operator_approval_intake_validator,
)


def test_step219_creates_validation_records_without_operator_input(isolated_project_root):
    root = isolated_project_root
    input_path = root / "config/operator_approval_input.json"
    if input_path.exists():
        input_path.unlink()
    result = execute_operator_approval_intake_validator(root, write_output=True)
    assert result.status == STEP219_STATUS_OK
    assert result.operator_approval_intake_validator_created is True
    assert result.approval_validation_performed is True
    assert result.operator_input_present is False
    assert result.source_intake_template_count > 0
    assert result.validation_record_count > 0
    assert result.validation_passed_count == 0
    assert result.validated_operator_approval_present is False


def test_step219_keeps_approval_upgrade_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    input_path = root / "config/operator_approval_input.json"
    if input_path.exists():
        input_path.unlink()
    result = execute_operator_approval_intake_validator(root, write_output=True)
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
    for record in result.records:
        assert record["validation_passed"] is False
        assert record["paper_execution_upgrade_allowed"] is False
        assert record["paper_order_execution_enabled"] is False
        assert record["adapter_routing_enabled"] is False
        assert record["limited_live_review_allowed"] is False
        assert record["live_trading_allowed"] is False
        assert record["strategy_registry_write_allowed"] is False
        assert record["promotion_allowed"] is False


def test_step219_validation_artifacts_are_valid_without_implicit_approval(isolated_project_root):
    root = isolated_project_root
    input_path = root / "config/operator_approval_input.json"
    if input_path.exists():
        input_path.unlink()
    execute_operator_approval_intake_validator(root, write_output=True)
    validation = validate_operator_approval_intake_validator(root)
    assert validation.status == STEP219_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step218_present is True
    assert validation.validation_records_json_exists is True
    assert validation.validation_records_jsonl_exists is True
    assert validation.validation_records_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_intake_templates_present is True
    assert validation.validation_records_present is True
    assert validation.validator_created is True
    assert validation.validation_performed is True
    assert validation.no_implicit_approval is True
    assert validation.no_approval_recorded is True
    assert validation.no_paper_execution_upgrade is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_limited_live_review is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_promotion_allowed is True
    assert validation.no_live_side_effects is True
