from pathlib import Path

from crypto_ai_system.feedback.promotion_gate_v2_review_only import (
    STEP215_STATUS_OK,
    STEP215_VALIDATION_OK,
    execute_promotion_gate_v2_review_only,
    validate_promotion_gate_v2_review_only,
)


def test_step215_creates_promotion_gate_decisions(isolated_project_root):
    root = isolated_project_root
    result = execute_promotion_gate_v2_review_only(root, write_output=True, allow_source_regeneration=True)
    assert result.status == STEP215_STATUS_OK
    assert result.promotion_gate_v2_review_only_created is True
    assert result.promotion_gate_applied is True
    assert result.promotion_gate_input_ready is True
    assert result.operator_review_required is True
    assert result.source_feedback_review_count > 0
    assert result.promotion_decision_count > 0
    assert result.average_promotion_readiness_score >= 0.0


def test_step215_keeps_promotion_registry_and_execution_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_promotion_gate_v2_review_only(root, write_output=True, allow_source_regeneration=True)
    assert result.promotion_allowed is False
    assert result.auto_strategy_promotion is False
    assert result.strategy_registry_write_allowed is False
    assert result.paper_execution_upgrade_allowed is False
    assert result.limited_live_review_allowed is False
    assert result.live_trading_allowed is False
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.external_api_call_performed is False
    assert result.live_order_executed is False
    assert result.real_adapter_call_performed is False
    assert result.telegram_real_send is False
    assert result.production_cutover_executable is False
    assert result.live_mode_enable_allowed is False
    for decision in result.decisions:
        assert decision["promotion_gate_applied"] is True
        assert decision["operator_review_required"] is True
        assert decision["promotion_allowed"] is False
        assert decision["auto_strategy_promotion"] is False
        assert decision["strategy_registry_write_allowed"] is False
        assert decision["paper_execution_upgrade_allowed"] is False
        assert decision["limited_live_review_allowed"] is False
        assert decision["live_trading_allowed"] is False
        assert decision["paper_order_execution_enabled"] is False
        assert decision["live_order_executed"] is False


def test_step215_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_promotion_gate_v2_review_only(root, write_output=True, allow_source_regeneration=True)
    validation = validate_promotion_gate_v2_review_only(root)
    assert validation.status == STEP215_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step214_present is True
    assert validation.promotion_decisions_json_exists is True
    assert validation.promotion_decisions_jsonl_exists is True
    assert validation.promotion_decisions_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_feedback_reviews_present is True
    assert validation.promotion_decisions_present is True
    assert validation.promotion_gate_created is True
    assert validation.promotion_gate_applied is True
    assert validation.promotion_gate_input_ready is True
    assert validation.operator_review_required is True
    assert validation.no_promotion_allowed is True
    assert validation.no_auto_strategy_promotion is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_paper_execution_upgrade is True
    assert validation.no_limited_live_review is True
    assert validation.no_live_trading is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_live_side_effects is True
