from pathlib import Path

from crypto_ai_system.ops.operator_final_enablement_approval_stub_review import (
    APPROVAL_STUB_MODE,
    STEP230_STATUS_OK,
    STEP230_VALIDATION_OK,
    execute_operator_final_enablement_approval_stub_review,
    validate_operator_final_enablement_approval_stub_review,
)


def test_step230_creates_operator_final_approval_stubs_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_operator_final_enablement_approval_stub_review(root, write_output=True)
    assert result.status == STEP230_STATUS_OK
    assert result.operator_final_approval_stub_review_created is True
    assert result.approval_stub_mode == APPROVAL_STUB_MODE
    assert result.approval_stub_only is True
    assert result.source_final_validation_record_count > 0
    assert result.approval_stub_count > 0


def test_step230_keeps_operator_approval_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_operator_final_enablement_approval_stub_review(root, write_output=True)
    assert result.operator_final_approval_submitted is False
    assert result.operator_final_approval_recorded is False
    assert result.enablement_request_submit_allowed is False
    assert result.enablement_request_submitted is False
    assert result.paper_execution_enablement_allowed is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.live_order_executed is False
    for row in result.approval_stubs:
        assert row["approval_stub_mode"] == APPROVAL_STUB_MODE
        assert row["operator_final_approval_stub_created"] is True
        assert row["operator_final_approval_template_created"] is True
        assert row["operator_final_approval_submitted"] is False
        assert row["operator_final_approval_recorded"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step230_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_operator_final_enablement_approval_stub_review(root, write_output=True)
    validation = validate_operator_final_enablement_approval_stub_review(root)
    assert validation.status == STEP230_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step229_present is True
    assert validation.approval_stubs_json_exists is True
    assert validation.approval_stubs_jsonl_exists is True
    assert validation.approval_stubs_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_final_validation_records_present is True
    assert validation.approval_stubs_present is True
    assert validation.approval_stub_review_created is True
    assert validation.approval_stub_mode_only is True
    assert validation.no_operator_final_approval_submitted is True
    assert validation.no_operator_final_approval_recorded is True
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
