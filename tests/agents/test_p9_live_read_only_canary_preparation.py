from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_read_only_canary_preparation import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_p9_live_read_only_canary_preparation_report,
    build_p9_negative_fixture_results,
    build_valid_p9_fixture_sources,
    persist_p9_live_read_only_canary_preparation,
)


def test_p9_latest_waits_when_p8_repeated_sessions_are_not_validated() -> None:
    cfg = load_config()
    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["p8_repeated_clean_signed_testnet_sessions_validated"] is False
    assert report["live_canary_preparation_ready_for_manual_approval_packet"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["actual_live_order_submitted"] is False
    assert report["secret_value_accessed"] is False
    assert "P9_BLOCK_P8_REPEATED_CLEAN_SIGNED_TESTNET_SESSIONS_NOT_VALIDATED" in report["block_reasons"]


def test_p9_valid_fixture_creates_review_ready_manual_approval_preparation_without_execution() -> None:
    cfg = load_config()
    sources = build_valid_p9_fixture_sources()
    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg, **sources)

    assert report["status"] == STATUS_READY_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["p8_repeated_clean_signed_testnet_sessions_validated"] is True
    assert report["live_read_only_probe_valid"] is True
    assert report["live_key_scope_validated"] is True
    assert report["monitoring_alerting_ready"] is True
    assert report["deployment_runbook_ready"] is True
    assert report["live_canary_preparation_ready_for_manual_approval_packet"] is True
    assert report["live_read_only_probe_actual_network_performed"] is False
    assert report["live_canary_approval_packet_created"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["actual_live_order_submitted"] is False
    assert report["live_order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False
    assert "P9_LIVE_READ_ONLY_PROBE_IS_METADATA_STUB_NOT_REAL_NETWORK" in report["warnings"]


def test_p9_blocks_live_probe_or_key_scope_unsafe_fields() -> None:
    cfg = load_config()
    sources = build_valid_p9_fixture_sources()
    sources["live_read_only_probe"] = {**sources["live_read_only_probe"], "place_order_enabled": True}

    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg, **sources)

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["live_canary_preparation_ready_for_manual_approval_packet"] is False
    assert "P9_BLOCK_LIVE_READ_ONLY_PROBE_PLACE_ORDER_ENABLED_NOT_FALSE" in report["block_reasons"]

    sources = build_valid_p9_fixture_sources()
    sources["live_key_scope_validation"] = {**sources["live_key_scope_validation"], "withdrawal_enabled": True}
    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P9_BLOCK_LIVE_KEY_SCOPE_WITHDRAWAL_ENABLED_NOT_FALSE" in report["block_reasons"]


def test_p9_blocks_monitoring_runbook_and_operator_enablement_attempts() -> None:
    cfg = load_config()
    sources = build_valid_p9_fixture_sources()
    sources["monitoring_alerting"] = {**sources["monitoring_alerting"], "external_notification_sent": True}
    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P9_BLOCK_MONITORING_EXTERNAL_NOTIFICATION_SENT" in report["block_reasons"]

    sources = build_valid_p9_fixture_sources()
    sources["deployment_runbook"] = {**sources["deployment_runbook"], "server_deployment_performed": True}
    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P9_BLOCK_DEPLOYMENT_RUNBOOK_ATTEMPTED_DEPLOYMENT" in report["block_reasons"]

    sources = build_valid_p9_fixture_sources()
    sources["operator_request"] = {**sources["operator_request"], "request_place_order_enabled": True}
    report = build_p9_live_read_only_canary_preparation_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P9_BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_ENABLEMENT" in report["block_reasons"]


def test_p9_negative_fixtures_all_block_fail_closed() -> None:
    cfg = load_config()
    negative = build_p9_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    for item in negative["fixture_results"].values():
        assert item["blocked_fail_closed"] is True
        assert item["live_canary_execution_enabled"] is False
        assert item["actual_live_order_submitted"] is False


def test_p9_persist_writes_latest_artifacts() -> None:
    cfg = load_config()
    report = persist_p9_live_read_only_canary_preparation(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert Path("storage/latest/p9_live_read_only_canary_preparation_report.json").exists()
    assert Path("storage/latest/p9_live_read_only_canary_preparation_summary.json").exists()
    assert Path("storage/latest/p9_live_read_only_canary_preparation_negative_fixture_results.json").exists()
    assert Path("storage/latest/p9_live_read_only_canary_preparation_registry_record.json").exists()
    summary = read_json(Path("storage/latest/p9_live_read_only_canary_preparation_summary.json"))
    assert summary["live_canary_execution_enabled"] is False
    assert summary["actual_live_order_submitted"] is False
