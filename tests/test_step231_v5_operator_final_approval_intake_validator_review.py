from pathlib import Path

from crypto_ai_system.ops.operator_final_approval_intake_validator_review import (
    DEFAULT_STATUS,
    INTAKE_VALIDATOR_MODE,
    STEP231_STATUS_OK,
    STEP231_VALIDATION_OK,
    execute_operator_final_approval_intake_validator_review,
    validate_operator_final_approval_intake_validator_review,
)


def test_step231_creates_operator_approval_intake_records_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_operator_final_approval_intake_validator_review(root, write_output=True)
    assert result.status == STEP231_STATUS_OK
    assert result.operator_final_approval_intake_validator_created is True
    assert result.intake_validator_mode == INTAKE_VALIDATOR_MODE
    assert result.intake_validator_review_only is True
    assert result.source_approval_stub_count > 0
    assert result.intake_record_count > 0


def test_step231_missing_input_defaults_not_approved_and_stays_disabled(isolated_project_root):
    root = isolated_project_root
    input_path = root / "config/operator_final_enablement_approval_input.json"
    if input_path.exists():
        input_path.unlink()
    result = execute_operator_final_approval_intake_validator_review(root, write_output=True)
    assert result.operator_input_present is False
    assert result.operator_final_approval_accepted is False
    assert result.operator_final_approval_recorded is False
    assert result.operator_final_approval_submitted is False
    assert result.paper_execution_enablement_allowed is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.live_trading_allowed is False
    for row in result.intake_records:
        assert row["operator_approval_status"] == DEFAULT_STATUS
        assert row["operator_final_approval_accepted"] is False
        assert row["operator_final_approval_recorded"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step231_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_operator_final_approval_intake_validator_review(root, write_output=True)
    validation = validate_operator_final_approval_intake_validator_review(root)
    assert validation.status == STEP231_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step230_present is True
    assert validation.intake_records_json_exists is True
    assert validation.intake_records_jsonl_exists is True
    assert validation.intake_records_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_approval_stubs_present is True
    assert validation.intake_records_present is True
    assert validation.intake_validator_created is True
    assert validation.intake_validator_mode_review_only is True
    assert validation.no_operator_final_approval_accepted is True
    assert validation.no_operator_final_approval_recorded is True
    assert validation.no_operator_final_approval_submitted is True
    assert validation.no_enablement_request_submitted is True
    assert validation.no_paper_execution_enablement_allowed is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_live_side_effects is True
