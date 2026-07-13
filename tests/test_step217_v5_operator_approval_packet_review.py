from pathlib import Path

from crypto_ai_system.ops.operator_approval_packet_review import (
    STEP217_STATUS_OK,
    STEP217_VALIDATION_OK,
    execute_operator_approval_packet_review,
    validate_operator_approval_packet_review,
)


def test_step217_creates_operator_approval_packets(isolated_project_root):
    root = isolated_project_root
    result = execute_operator_approval_packet_review(root, write_output=True)
    assert result.status == STEP217_STATUS_OK
    assert result.operator_approval_packet_created is True
    assert result.operator_packet_review_only is True
    assert result.manual_approval_required is True
    assert result.operator_review_required is True
    assert result.source_upgrade_review_count > 0
    assert result.approval_packet_count > 0


def test_step217_keeps_operator_approval_and_execution_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_operator_approval_packet_review(root, write_output=True)
    assert result.operator_approved is False
    assert result.approval_recorded is False
    assert result.paper_execution_upgrade_allowed is False
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.adapter_routing_enabled is False
    assert result.shadow_execution_enabled is False
    assert result.limited_live_review_allowed is False
    assert result.live_trading_allowed is False
    assert result.strategy_registry_write_allowed is False
    assert result.promotion_allowed is False
    assert result.auto_strategy_promotion is False
    assert result.external_api_call_performed is False
    assert result.live_order_executed is False
    assert result.real_adapter_call_performed is False
    assert result.telegram_real_send is False
    assert result.production_cutover_executable is False
    assert result.live_mode_enable_allowed is False
    for packet in result.packets:
        assert packet["manual_approval_required"] is True
        assert packet["operator_review_required"] is True
        assert packet["operator_approved"] is False
        assert packet["approval_recorded"] is False
        assert packet["paper_execution_upgrade_allowed"] is False
        assert packet["paper_order_execution_enabled"] is False
        assert packet["adapter_routing_enabled"] is False
        assert packet["shadow_execution_enabled"] is False
        assert packet["limited_live_review_allowed"] is False
        assert packet["live_trading_allowed"] is False
        assert packet["strategy_registry_write_allowed"] is False
        assert packet["promotion_allowed"] is False


def test_step217_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_operator_approval_packet_review(root, write_output=True)
    validation = validate_operator_approval_packet_review(root)
    assert validation.status == STEP217_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step216_present is True
    assert validation.approval_packets_json_exists is True
    assert validation.approval_packets_jsonl_exists is True
    assert validation.approval_packets_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_upgrade_reviews_present is True
    assert validation.approval_packets_present is True
    assert validation.operator_approval_packet_created is True
    assert validation.review_only_mode is True
    assert validation.manual_approval_required is True
    assert validation.operator_review_required is True
    assert validation.no_operator_approval_recorded is True
    assert validation.no_paper_execution_upgrade is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_limited_live_review is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_promotion_allowed is True
    assert validation.no_live_side_effects is True
