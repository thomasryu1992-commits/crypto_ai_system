from pathlib import Path

from crypto_ai_system.ops.enablement_pre_submit_review import (
    PRE_SUBMIT_REVIEW_MODE,
    STEP233_STATUS_OK,
    STEP233_VALIDATION_OK,
    execute_enablement_pre_submit_review,
    validate_enablement_pre_submit_review,
)


def test_step233_creates_enablement_pre_submit_review_records(isolated_project_root):
    root = isolated_project_root
    result = execute_enablement_pre_submit_review(root, write_output=True)
    assert result.status == STEP233_STATUS_OK
    assert result.enablement_pre_submit_review_created is True
    assert result.pre_submit_review_mode == PRE_SUBMIT_REVIEW_MODE
    assert result.pre_submit_review_only is True
    assert result.source_bridge_record_count > 0
    assert result.pre_submit_record_count > 0


def test_step233_keeps_submit_enablement_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_enablement_pre_submit_review(root, write_output=True)
    assert result.pre_submit_review_passed is False
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
    for row in result.pre_submit_records:
        assert row["pre_submit_review_mode"] == PRE_SUBMIT_REVIEW_MODE
        assert row["pre_submit_record_created"] is True
        assert row["pre_submit_review_passed"] is False
        assert row["enablement_request_submitted"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["live_trading_allowed"] is False


def test_step233_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_enablement_pre_submit_review(root, write_output=True)
    validation = validate_enablement_pre_submit_review(root)
    assert validation.status == STEP233_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step232_present is True
    assert validation.pre_submit_records_json_exists is True
    assert validation.pre_submit_records_jsonl_exists is True
    assert validation.pre_submit_records_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_bridge_records_present is True
    assert validation.pre_submit_records_present is True
    assert validation.pre_submit_review_created is True
    assert validation.pre_submit_review_mode_review_only is True
    assert validation.no_pre_submit_review_passed is True
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
