from pathlib import Path

from crypto_ai_system.ops.enablement_submit_dry_run_review import (
    DRY_RUN_MODE,
    STEP237_STATUS_OK,
    STEP237_VALIDATION_OK,
    execute_enablement_submit_dry_run_review,
    validate_enablement_submit_dry_run_review,
)


def test_step237_creates_enablement_submit_dry_run_records_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_enablement_submit_dry_run_review(root, write_output=True)
    assert result.status == STEP237_STATUS_OK
    assert result.enablement_submit_dry_run_review_created is True
    assert result.dry_run_mode == DRY_RUN_MODE
    assert result.dry_run_review_only is True
    assert result.dry_run_artifact_created is True
    assert result.source_submit_gate_record_count > 0
    assert result.dry_run_record_count > 0


def test_step237_keeps_dry_run_submit_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_enablement_submit_dry_run_review(root, write_output=True)
    assert result.dry_run_passed is False
    assert result.submit_gate_passed is False
    assert result.submit_gate_opened is False
    assert result.enablement_request_submit_allowed is False
    assert result.enablement_request_submitted is False
    assert result.paper_execution_enablement_allowed is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.external_api_call_performed is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.live_order_executed is False
    for row in result.dry_run_records:
        assert row["dry_run_mode"] == DRY_RUN_MODE
        assert row["dry_run_record_created"] is True
        assert row["dry_run_artifact_created"] is True
        assert row["dry_run_passed"] is False
        assert row["enablement_request_submitted"] is False
        assert row["paper_execution_enabled"] is False
        assert row["paper_order_execution_enabled"] is False
        assert row["adapter_routing_enabled"] is False
        assert row["shadow_execution_enabled"] is False
        assert row["external_api_call_performed"] is False
        assert row["live_trading_allowed"] is False


def test_step237_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_enablement_submit_dry_run_review(root, write_output=True)
    validation = validate_enablement_submit_dry_run_review(root)
    assert validation.status == STEP237_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step236_present is True
    assert validation.dry_run_records_json_exists is True
    assert validation.dry_run_records_jsonl_exists is True
    assert validation.dry_run_records_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_submit_gate_records_present is True
    assert validation.dry_run_records_present is True
    assert validation.dry_run_review_created is True
    assert validation.dry_run_mode_review_only is True
    assert validation.dry_run_artifact_created is True
    assert validation.no_dry_run_passed is True
    assert validation.no_submit_gate_passed is True
    assert validation.no_submit_gate_opened is True
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
