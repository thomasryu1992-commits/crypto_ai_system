from pathlib import Path

from crypto_ai_system.ops.paper_execution_mode_pre_enablement_audit_review import (
    PRE_ENABLEMENT_AUDIT_MODE,
    STEP227_STATUS_OK,
    STEP227_VALIDATION_OK,
    execute_paper_execution_mode_pre_enablement_audit_review,
    validate_paper_execution_mode_pre_enablement_audit_review,
)


def test_step227_creates_pre_enablement_audit_records_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_mode_pre_enablement_audit_review(root, write_output=True)
    assert result.status == STEP227_STATUS_OK
    assert result.pre_enablement_audit_review_created is True
    assert result.audit_mode == PRE_ENABLEMENT_AUDIT_MODE
    assert result.audit_review_only is True
    assert result.source_shadow_ready_decision_count > 0
    assert result.audit_record_count > 0


def test_step227_keeps_audit_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_mode_pre_enablement_audit_review(root, write_output=True)
    assert result.pre_enablement_audit_passed is False
    assert result.paper_execution_enablement_allowed is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.live_order_executed is False
    for row in result.audit_records:
        assert row["audit_mode"] == PRE_ENABLEMENT_AUDIT_MODE
        assert row["audit_record_created"] is True
        assert row["pre_enablement_audit_passed"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step227_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_execution_mode_pre_enablement_audit_review(root, write_output=True)
    validation = validate_paper_execution_mode_pre_enablement_audit_review(root)
    assert validation.status == STEP227_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step226_present is True
    assert validation.audit_records_json_exists is True
    assert validation.audit_records_jsonl_exists is True
    assert validation.audit_records_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_shadow_ready_decisions_present is True
    assert validation.audit_records_present is True
    assert validation.audit_review_created is True
    assert validation.audit_mode_review_only is True
    assert validation.no_pre_enablement_audit_passed is True
    assert validation.no_paper_execution_enablement_allowed is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_live_side_effects is True
