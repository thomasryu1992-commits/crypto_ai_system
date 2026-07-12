from pathlib import Path

from crypto_ai_system.ops.paper_execution_enablement_request_stub_review import (
    REQUEST_STUB_MODE,
    STEP228_STATUS_OK,
    STEP228_VALIDATION_OK,
    execute_paper_execution_enablement_request_stub_review,
    validate_paper_execution_enablement_request_stub_review,
)


def test_step228_creates_enablement_request_stubs_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_enablement_request_stub_review(root, write_output=True)
    assert result.status == STEP228_STATUS_OK
    assert result.paper_execution_enablement_request_stub_review_created is True
    assert result.request_stub_mode == REQUEST_STUB_MODE
    assert result.request_stub_only is True
    assert result.source_audit_record_count > 0
    assert result.request_stub_count > 0


def test_step228_keeps_request_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_enablement_request_stub_review(root, write_output=True)
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
    for row in result.request_stubs:
        assert row["request_stub_mode"] == REQUEST_STUB_MODE
        assert row["request_stub_created"] is True
        assert row["enablement_request_created"] is True
        assert row["enablement_request_submitted"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step228_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_execution_enablement_request_stub_review(root, write_output=True)
    validation = validate_paper_execution_enablement_request_stub_review(root)
    assert validation.status == STEP228_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step227_present is True
    assert validation.request_stubs_json_exists is True
    assert validation.request_stubs_jsonl_exists is True
    assert validation.request_stubs_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_audit_records_present is True
    assert validation.request_stubs_present is True
    assert validation.request_stub_review_created is True
    assert validation.request_stub_mode_only is True
    assert validation.no_enablement_request_submitted is True
    assert validation.no_paper_execution_enablement_allowed is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_live_side_effects is True
