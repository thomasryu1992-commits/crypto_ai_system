from pathlib import Path

from crypto_ai_system.ops.approval_to_enablement_bridge_review import (
    BRIDGE_MODE,
    STEP232_STATUS_OK,
    STEP232_VALIDATION_OK,
    execute_approval_to_enablement_bridge_review,
    validate_approval_to_enablement_bridge_review,
)


def test_step232_creates_approval_to_enablement_bridge_records_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_approval_to_enablement_bridge_review(root, write_output=True)
    assert result.status == STEP232_STATUS_OK
    assert result.approval_to_enablement_bridge_review_created is True
    assert result.bridge_mode == BRIDGE_MODE
    assert result.bridge_review_only is True
    assert result.source_intake_record_count > 0
    assert result.bridge_record_count > 0


def test_step232_keeps_bridge_enablement_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_approval_to_enablement_bridge_review(root, write_output=True)
    assert result.approval_bridge_passed is False
    assert result.operator_final_approval_accepted is False
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
    for row in result.bridge_records:
        assert row["bridge_mode"] == BRIDGE_MODE
        assert row["bridge_record_created"] is True
        assert row["approval_bridge_passed"] is False
        assert row["operator_final_approval_accepted"] is False
        assert row["operator_final_approval_recorded"] is False
        assert row["enablement_request_submitted"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step232_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_approval_to_enablement_bridge_review(root, write_output=True)
    validation = validate_approval_to_enablement_bridge_review(root)
    assert validation.status == STEP232_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step231_present is True
    assert validation.bridge_records_json_exists is True
    assert validation.bridge_records_jsonl_exists is True
    assert validation.bridge_records_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_intake_records_present is True
    assert validation.bridge_records_present is True
    assert validation.bridge_review_created is True
    assert validation.bridge_mode_review_only is True
    assert validation.no_approval_bridge_passed is True
    assert validation.no_operator_final_approval_accepted is True
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
