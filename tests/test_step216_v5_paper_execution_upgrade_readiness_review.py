from pathlib import Path

from crypto_ai_system.feedback.paper_execution_upgrade_readiness_review import (
    STEP216_STATUS_OK,
    STEP216_VALIDATION_OK,
    execute_paper_execution_upgrade_readiness_review,
    validate_paper_execution_upgrade_readiness_review,
)


def test_step216_creates_upgrade_readiness_reviews(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_upgrade_readiness_review(root, write_output=True, allow_source_regeneration=True)
    assert result.status == STEP216_STATUS_OK
    assert result.paper_execution_upgrade_readiness_review_created is True
    assert result.readiness_checklist_applied is True
    assert result.operator_review_required is True
    assert result.manual_approval_required is True
    assert result.source_promotion_decision_count > 0
    assert result.upgrade_review_count > 0
    assert result.average_upgrade_readiness_score >= 0.0
    assert result.evidence_files_required_count >= 1


def test_step216_keeps_upgrade_execution_and_live_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_execution_upgrade_readiness_review(root, write_output=True, allow_source_regeneration=True)
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
    for review in result.reviews:
        assert review["operator_review_required"] is True
        assert review["manual_approval_required"] is True
        assert review["paper_execution_upgrade_allowed"] is False
        assert review["paper_order_execution_enabled"] is False
        assert review["adapter_routing_enabled"] is False
        assert review["shadow_execution_enabled"] is False
        assert review["limited_live_review_allowed"] is False
        assert review["live_trading_allowed"] is False
        assert review["strategy_registry_write_allowed"] is False
        assert review["promotion_allowed"] is False


def test_step216_validation_artifacts_are_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_execution_upgrade_readiness_review(root, write_output=True, allow_source_regeneration=True)
    validation = validate_paper_execution_upgrade_readiness_review(root)
    assert validation.status == STEP216_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step215_present is True
    assert validation.upgrade_reviews_json_exists is True
    assert validation.upgrade_reviews_jsonl_exists is True
    assert validation.upgrade_reviews_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.source_promotion_decisions_present is True
    assert validation.upgrade_reviews_present is True
    assert validation.readiness_review_created is True
    assert validation.readiness_checklist_applied is True
    assert validation.operator_review_required is True
    assert validation.manual_approval_required is True
    assert validation.no_paper_execution_upgrade is True
    assert validation.no_paper_order_execution is True
    assert validation.no_adapter_routing is True
    assert validation.no_shadow_execution is True
    assert validation.no_limited_live_review is True
    assert validation.no_live_trading is True
    assert validation.no_strategy_registry_write is True
    assert validation.no_promotion_allowed is True
    assert validation.no_live_side_effects is True
