from pathlib import Path

from crypto_ai_system.ops.final_config_apply_gate_review_only import FINAL_GATE_MODE, STEP225_STATUS_OK, STEP225_VALIDATION_OK, execute_final_config_apply_gate_review_only, validate_final_config_apply_gate_review_only


def test_step225_creates_final_gate_decisions_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_final_config_apply_gate_review_only(root, write_output=True)
    assert result.status == STEP225_STATUS_OK
    assert result.final_config_apply_gate_review_created is True
    assert result.final_gate_mode == FINAL_GATE_MODE
    assert result.final_gate_review_only is True
    assert result.source_apply_stub_count > 0
    assert result.final_gate_decision_count > 0


def test_step225_keeps_apply_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_final_config_apply_gate_review_only(root, write_output=True)
    assert result.final_apply_gate_passed is False
    assert result.config_apply_allowed is False
    assert result.config_applied is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.live_trading_allowed is False
    for decision in result.decisions:
        assert decision["final_gate_mode"] == FINAL_GATE_MODE
        assert decision["final_gate_decision_created"] is True
        assert decision["final_apply_gate_passed"] is False
        assert decision["config_apply_allowed"] is False
        assert decision["config_applied"] is False
        assert decision["paper_execution_enabled"] is False
        assert decision["paper_order_execution_enabled"] is False


def test_step225_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_final_config_apply_gate_review_only(root, write_output=True)
    validation = validate_final_config_apply_gate_review_only(root)
    assert validation.status == STEP225_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step224_present is True
    assert validation.final_gate_decisions_json_exists is True
    assert validation.final_gate_decisions_jsonl_exists is True
    assert validation.final_gate_decisions_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_apply_stubs_present is True
    assert validation.final_gate_decisions_present is True
    assert validation.final_gate_review_created is True
    assert validation.final_gate_mode_review_only is True
    assert validation.no_final_apply_gate_passed is True
    assert validation.no_config_apply_allowed is True
    assert validation.no_config_applied is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_paper_order_execution is True
