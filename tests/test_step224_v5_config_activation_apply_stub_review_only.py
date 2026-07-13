from pathlib import Path

from crypto_ai_system.ops.config_activation_apply_stub_review_only import (
    APPLY_MODE_STUB_ONLY,
    STEP224_STATUS_OK,
    STEP224_VALIDATION_OK,
    execute_config_activation_apply_stub_review_only,
    validate_config_activation_apply_stub_review_only,
)


def test_step224_creates_apply_stubs_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_config_activation_apply_stub_review_only(root, write_output=True)
    assert result.status == STEP224_STATUS_OK
    assert result.config_activation_apply_stub_review_created is True
    assert result.apply_mode == APPLY_MODE_STUB_ONLY
    assert result.apply_stub_only is True
    assert result.source_activation_candidate_count > 0
    assert result.apply_stub_count > 0


def test_step224_keeps_apply_activation_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_config_activation_apply_stub_review_only(root, write_output=True)
    assert result.apply_request_submitted is False
    assert result.config_activation_allowed is False
    assert result.config_activated is False
    assert result.config_apply_allowed is False
    assert result.config_applied is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.live_order_executed is False
    for stub in result.stubs:
        assert stub["apply_mode"] == APPLY_MODE_STUB_ONLY
        assert stub["config_activation_apply_stub_created"] is True
        assert stub["apply_request_created"] is True
        assert stub["apply_request_submitted"] is False
        assert stub["config_activation_allowed"] is False
        assert stub["config_activated"] is False
        assert stub["paper_execution_enabled"] is False
        assert stub["paper_order_execution_enabled"] is False
        assert stub["adapter_routing_enabled"] is False
        assert stub["live_trading_allowed"] is False


def test_step224_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_config_activation_apply_stub_review_only(root, write_output=True)
    validation = validate_config_activation_apply_stub_review_only(root)
    assert validation.status == STEP224_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step223_present is True
    assert validation.apply_stubs_json_exists is True
    assert validation.apply_stubs_jsonl_exists is True
    assert validation.apply_stubs_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_activation_candidates_present is True
    assert validation.apply_stubs_present is True
    assert validation.apply_stub_review_created is True
    assert validation.apply_mode_stub_only is True
    assert validation.no_apply_request_submitted is True
    assert validation.no_config_activation_allowed is True
    assert validation.no_config_activated is True
    assert validation.no_config_apply_allowed is True
    assert validation.no_config_applied is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_live_side_effects is True
