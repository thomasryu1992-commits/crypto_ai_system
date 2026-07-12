from pathlib import Path

from crypto_ai_system.ops.enablement_submit_decision_stub_review import (
    STEP234_STATUS_OK,
    STEP234_VALIDATION_OK,
    SUBMIT_DECISION_MODE,
    execute_enablement_submit_decision_stub_review,
    validate_enablement_submit_decision_stub_review,
)


def test_step234_creates_enablement_submit_decision_stubs(isolated_project_root):
    root = isolated_project_root
    result = execute_enablement_submit_decision_stub_review(root, write_output=True)
    assert result.status == STEP234_STATUS_OK
    assert result.enablement_submit_decision_stub_created is True
    assert result.submit_decision_mode == SUBMIT_DECISION_MODE
    assert result.submit_decision_stub_only is True
    assert result.source_pre_submit_record_count > 0
    assert result.submit_decision_count > 0


def test_step234_keeps_submit_decision_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_enablement_submit_decision_stub_review(root, write_output=True)
    assert result.submit_decision_approved is False
    assert result.submit_decision_recorded is False
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
    for row in result.submit_decisions:
        assert row["submit_decision_mode"] == SUBMIT_DECISION_MODE
        assert row["submit_decision_record_created"] is True
        assert row["submit_decision_template_created"] is True
        assert row["submit_decision_approved"] is False
        assert row["submit_decision_recorded"] is False
        assert row["enablement_request_submitted"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step234_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_enablement_submit_decision_stub_review(root, write_output=True)
    validation = validate_enablement_submit_decision_stub_review(root)
    assert validation.status == STEP234_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step233_present is True
    assert validation.submit_decisions_json_exists is True
    assert validation.submit_decisions_jsonl_exists is True
    assert validation.submit_decisions_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_pre_submit_records_present is True
    assert validation.submit_decisions_present is True
    assert validation.submit_decision_stub_created is True
    assert validation.submit_decision_mode_stub_only is True
    assert validation.no_submit_decision_approved is True
    assert validation.no_submit_decision_recorded is True
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
