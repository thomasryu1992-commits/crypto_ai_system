from pathlib import Path

from crypto_ai_system.ops.paper_execution_enablement_request_final_validator_review import (
    FINAL_VALIDATOR_MODE,
    STEP229_STATUS_OK,
    STEP229_VALIDATION_OK,
    execute_paper_execution_enablement_request_final_validator_review,
    validate_paper_execution_enablement_request_final_validator_review,
)


def test_step229_creates_final_validation_records_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_enablement_request_final_validator_review(root, write_output=True)
    assert result.status == STEP229_STATUS_OK
    assert result.final_validator_review_created is True
    assert result.final_validator_mode == FINAL_VALIDATOR_MODE
    assert result.final_validator_review_only is True
    assert result.source_request_stub_count > 0
    assert result.final_validation_record_count > 0


def test_step229_keeps_final_validation_request_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_enablement_request_final_validator_review(root, write_output=True)
    assert result.final_enablement_request_validation_passed is False
    assert result.enablement_request_submit_allowed is False
    assert result.enablement_request_submitted is False
    assert result.paper_execution_enablement_allowed is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.live_order_executed is False
    for row in result.validation_records:
        assert row["final_validator_mode"] == FINAL_VALIDATOR_MODE
        assert row["final_validation_record_created"] is True
        assert row["final_enablement_request_validation_passed"] is False
        assert row["enablement_request_submitted"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step229_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_execution_enablement_request_final_validator_review(root, write_output=True)
    validation = validate_paper_execution_enablement_request_final_validator_review(root)
    assert validation.status == STEP229_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step228_present is True
    assert validation.final_validation_json_exists is True
    assert validation.final_validation_jsonl_exists is True
    assert validation.final_validation_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_request_stubs_present is True
    assert validation.final_validation_records_present is True
    assert validation.final_validator_review_created is True
    assert validation.final_validator_mode_review_only is True
    assert validation.no_final_enablement_request_validation_passed is True
    assert validation.no_enablement_request_submit_allowed is True
    assert validation.no_enablement_request_submitted is True
    assert validation.no_paper_execution_enablement_allowed is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_live_side_effects is True
