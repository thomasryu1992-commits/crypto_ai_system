from pathlib import Path

from crypto_ai_system.ops.paper_execution_mode_shadow_ready_review import (
    SHADOW_READY_MODE,
    STEP226_STATUS_OK,
    STEP226_VALIDATION_OK,
    execute_paper_execution_mode_shadow_ready_review,
    validate_paper_execution_mode_shadow_ready_review,
)


def test_step226_creates_shadow_ready_decisions_review_only(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_mode_shadow_ready_review(root, write_output=True)
    assert result.status == STEP226_STATUS_OK
    assert result.paper_execution_mode_shadow_ready_review_created is True
    assert result.shadow_ready_mode == SHADOW_READY_MODE
    assert result.shadow_ready_review_only is True
    assert result.source_final_gate_decision_count > 0
    assert result.shadow_ready_decision_count > 0


def test_step226_keeps_shadow_ready_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_mode_shadow_ready_review(root, write_output=True)
    assert result.shadow_ready_mode_allowed is False
    assert result.shadow_ready_mode_enabled is False
    assert result.paper_execution_enabled is False
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.live_order_executed is False
    for decision in result.decisions:
        assert decision["shadow_ready_mode"] == SHADOW_READY_MODE
        assert decision["shadow_ready_decision_created"] is True
        assert decision["shadow_ready_mode_allowed"] is False
        assert decision["shadow_ready_mode_enabled"] is False
        assert decision["paper_execution_enabled"] is False
        assert decision["paper_order_execution_enabled"] is False
        assert decision["adapter_routing_enabled"] is False
        assert decision["shadow_execution_enabled"] is False
        assert decision["live_trading_allowed"] is False


def test_step226_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_execution_mode_shadow_ready_review(root, write_output=True)
    validation = validate_paper_execution_mode_shadow_ready_review(root)
    assert validation.status == STEP226_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step225_present is True
    assert validation.shadow_ready_json_exists is True
    assert validation.shadow_ready_jsonl_exists is True
    assert validation.shadow_ready_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_final_gate_decisions_present is True
    assert validation.shadow_ready_decisions_present is True
    assert validation.shadow_ready_review_created is True
    assert validation.shadow_ready_mode_review_only is True
    assert validation.no_shadow_ready_mode_allowed is True
    assert validation.no_shadow_ready_mode_enabled is True
    assert validation.no_paper_execution_enabled is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_live_side_effects is True
