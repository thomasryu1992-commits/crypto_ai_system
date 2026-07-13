from pathlib import Path

from crypto_ai_system.backtest.paper_signal_replay import (
    STEP210_STATUS_OK,
    STEP210_VALIDATION_OK,
    execute_paper_signal_replay,
    validate_paper_signal_replay,
)


def test_step210_creates_paper_signal_replay_outputs(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_signal_replay(root, write_output=True)
    assert result.status == STEP210_STATUS_OK
    assert result.paper_signal_replay_performed is True
    assert result.eligible_queue_item_count > 0
    assert result.replay_summary_count > 0
    assert result.replay_event_count > 0


def test_step210_keeps_execution_and_live_boundaries_disabled(isolated_project_root):
    root = isolated_project_root
    result = execute_paper_signal_replay(root, write_output=True)
    assert result.paper_order_execution_enabled is False
    assert result.paper_trade_execution_enabled is False
    assert result.auto_strategy_promotion is False
    assert result.external_api_call_performed is False
    assert result.live_order_executed is False
    assert result.real_adapter_call_performed is False
    assert result.telegram_real_send is False
    assert result.production_cutover_executable is False
    assert result.live_mode_enable_allowed is False
    for summary in result.summaries:
        assert summary["paper_order_execution_enabled"] is False
        assert summary["paper_trade_execution_enabled"] is False
        assert summary["promotion_allowed"] is False
        assert summary["live_trading_allowed"] is False


def test_step210_validation_artifacts_exist_and_hash_is_valid(isolated_project_root):
    root = isolated_project_root
    execute_paper_signal_replay(root, write_output=True)
    validation = validate_paper_signal_replay(root)
    assert validation.status == STEP210_VALIDATION_OK
    assert validation.result_hash_valid is True
    assert validation.source_step209_present is True
    assert validation.replay_events_json_exists is True
    assert validation.summary_json_exists is True
    assert validation.summary_csv_exists is True
    assert validation.markdown_report_exists is True
    assert validation.replay_events_exist is True
    assert validation.no_paper_order_execution is True
    assert validation.no_paper_trade_execution is True
    assert validation.no_auto_promotion is True
    assert validation.no_live_side_effects is True
