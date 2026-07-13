from __future__ import annotations

import shutil
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.monitoring_alerting import (
    ALERT_DATA_HEALTH,
    ALERT_LIVE_CANARY_RECONCILIATION,
    ALERT_ORDER_SUBMISSION_BLOCKED,
    BLOCK_NOTIFICATION_SEND_ATTEMPT,
    BLOCK_UNSAFE_SIDE_EFFECT,
    MONITORING_ALERTING_REGISTRY_NAME,
    STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_RECORDED_REVIEW_ONLY,
    MonitoringAlertingPolicy,
    build_monitoring_alerting_report,
    persist_monitoring_alerting_report,
    run_monitoring_alerting_latest,
)
from crypto_ai_system.registry.base_registry import registry_path


def _data_health() -> dict:
    return {"status": "UNHEALTHY", "allow_trading": False}


def _risk_guard() -> dict:
    return {"status": "NORMAL", "allow_new_position": True, "daily_pnl_r": 0.0, "problems": []}


def _order() -> dict:
    return {"status": "NO_ORDER", "order_intent_created": False}


def _signed_rec() -> dict:
    return {"status": "SIGNED_TESTNET_RECONCILIATION_BLOCKED_NO_SUBMISSION", "promotion_blocker": "BLOCK_TESTNET_PROMOTION_EXECUTION_NOT_SUBMITTED"}


def _signed_close() -> dict:
    return {"status": "SIGNED_TESTNET_SESSION_CLOSE_REPORT_BLOCKED", "promotion_recommendation": "block_signed_testnet_promotion", "api_error_count": 0}


def _live_exec() -> dict:
    return {"status": "NO_LIVE_CANARY_ORDER_SUBMITTED", "submitted_to_exchange": False}


def _live_rec() -> dict:
    return {"status": "LIVE_CANARY_RECONCILIATION_BLOCKED_NO_SUBMISSION", "promotion_blocker": "BLOCK_LIVE_CANARY_PROMOTION_EXECUTION_NOT_SUBMITTED"}


def test_step316_builds_review_only_alert_report() -> None:
    report = build_monitoring_alerting_report(
        data_health=_data_health(),
        risk_guard=_risk_guard(),
        order=_order(),
        signed_testnet_reconciliation=_signed_rec(),
        signed_testnet_session_close=_signed_close(),
        live_canary_order_executor=_live_exec(),
        live_canary_reconciliation=_live_rec(),
    )
    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["heartbeat_ok"] is True
    assert report["critical_alert_count"] >= 2
    assert report["warning_alert_count"] >= 1
    alert_types = {alert["alert_type"] for alert in report["alerts"]}
    assert ALERT_DATA_HEALTH in alert_types
    assert ALERT_ORDER_SUBMISSION_BLOCKED in alert_types
    assert ALERT_LIVE_CANARY_RECONCILIATION in alert_types
    assert report["telegram_message_sent"] is False
    assert report["external_notification_sent"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False


def test_step316_blocks_notification_send_attempt() -> None:
    report = build_monitoring_alerting_report(
        data_health=_data_health(),
        risk_guard=_risk_guard(),
        order=_order(),
        live_canary_order_executor=_live_exec(),
        live_canary_reconciliation=_live_rec(),
        policy=MonitoringAlertingPolicy(telegram_message_sent=True),
    )
    assert report["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert BLOCK_UNSAFE_SIDE_EFFECT in report["block_reasons"]
    assert BLOCK_NOTIFICATION_SEND_ATTEMPT in report["block_reasons"]
    assert report["telegram_message_sent"] is False


def test_step316_persists_registry_record(tmp_path: Path) -> None:
    root = Path.cwd()
    work = tmp_path / "repo"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "dist", "storage", "data/reports", "data/stores")
    shutil.copytree(root, work, ignore=ignore)
    cfg = load_config(work)
    report = build_monitoring_alerting_report(data_health=_data_health(), risk_guard=_risk_guard(), order=_order())
    persisted = persist_monitoring_alerting_report(cfg, report)
    assert (work / "storage/latest/monitoring_alerting_report.json").exists()
    assert (work / "storage/latest/monitoring_alerting_registry_record.json").exists()
    assert registry_path(cfg, MONITORING_ALERTING_REGISTRY_NAME).exists()
    assert persisted["monitoring_alerting_registry_record_id"]
    assert persisted["monitoring_alerting_registry_record_sha256"]


def test_step316_run_latest_reads_storage_inputs(tmp_path: Path) -> None:
    root = Path.cwd()
    work = tmp_path / "repo"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "dist", "storage", "data/reports", "data/stores")
    shutil.copytree(root, work, ignore=ignore)
    latest = work / "storage/latest"
    atomic_write_json(latest / "data_health.json", _data_health())
    atomic_write_json(latest / "risk_status.json", _risk_guard())
    atomic_write_json(latest / "order_result.json", _order())
    atomic_write_json(latest / "live_canary_order_execution_record.json", _live_exec())
    atomic_write_json(latest / "live_canary_reconciliation_record.json", _live_rec())
    result = run_monitoring_alerting_latest(project_root=work)
    assert result["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert result["alert_count"] >= 4
    assert result["live_canary_reconciliation_status"] == _live_rec()["status"]
