from pathlib import Path

from crypto_ai_system.backtest.paper_observation_queue import (
    STEP209_STATUS_OK,
    STEP209_VALIDATION_OK,
    execute_paper_observation_queue,
    validate_paper_observation_queue,
)


def test_step209_creates_paper_observation_queue(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_observation_queue(root, write_output=True)
    assert result.status == STEP209_STATUS_OK
    assert result.queue_item_count > 0
    assert result.paper_observation_queue_created is True
    assert result.paper_tracking_enabled is True
    assert result.paper_signal_observation_enabled is True


def test_step209_does_not_enable_paper_or_live_execution(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_observation_queue(root, write_output=True)
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.auto_strategy_promotion is False
    assert result.external_api_call_performed is False
    assert result.live_order_executed is False
    assert result.real_adapter_call_performed is False
    assert result.telegram_real_send is False
    assert result.production_cutover_executable is False
    assert result.live_mode_enable_allowed is False
    assert all(item["paper_order_execution_allowed"] is False for item in result.queue_items)
    assert all(item["live_trading_allowed"] is False for item in result.queue_items)


def test_step209_requires_operator_review_and_source_policy(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_observation_queue(root, write_output=True)
    assert result.source_policy_enforced is True
    assert result.operator_review_required is True
    assert all(item["requires_operator_review"] is True for item in result.queue_items)
    assert all(item["observation_mode"] == "TRACK_SIGNALS_ONLY" for item in result.queue_items)


def test_step209_validation_artifacts_exist(isolated_project_root):
    root = isolated_project_root
    execute_paper_observation_queue(root, write_output=True)
    validation = validate_paper_observation_queue(root)
    assert validation.status == STEP209_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step208_present is True
    assert validation.queue_json_exists is True
    assert validation.queue_csv_exists is True
    assert validation.queue_markdown_exists is True
    assert validation.no_paper_order_execution is True
    assert validation.no_paper_trade_execution is True
