from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_canary_one_order_execution_boundary import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_REVIEW_ONLY_NO_SUBMIT,
    STATUS_WAITING_REVIEW_ONLY,
    build_p10_live_canary_one_order_execution_boundary_report,
    build_p10_negative_fixture_results,
    build_valid_p10_fixture_sources,
    persist_p10_live_canary_one_order_execution_boundary,
)


def test_p10_latest_waits_when_p9_live_canary_preparation_is_not_ready() -> None:
    cfg = load_config()
    report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["p9_live_canary_preparation_ready"] is False
    assert report["p10_live_canary_one_order_execution_boundary_ready"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["actual_live_order_submitted"] is False
    assert report["live_order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False
    assert "P10_BLOCK_P9_LIVE_CANARY_PREPARATION_NOT_READY" in report["block_reasons"]


def test_p10_valid_fixture_creates_review_only_boundary_without_submit() -> None:
    cfg = load_config()
    sources = build_valid_p10_fixture_sources()
    report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg, **sources)

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["p9_live_canary_preparation_ready"] is True
    assert report["p10_live_canary_one_order_execution_boundary_ready"] is True
    assert report["live_canary_approval_packet_valid_review_only"] is True
    assert report["live_canary_one_order_boundary_valid"] is True
    assert report["fresh_data_snapshot_confirmed"] is True
    assert report["research_signal_v2_created"] is True
    assert report["signal_qa_passed"] is True
    assert report["hot_path_preorder_risk_gate_passed"] is True
    assert report["hot_path_preorder_risk_gate_fresh"] is True
    assert report["idempotency_key_present"] is True
    assert report["duplicate_submit_lock_engaged"] is True
    assert report["post_submit_relock_planned"] is True
    assert report["live_canary_order_allowed_by_this_module"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["actual_live_order_submitted"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["live_order_endpoint_called"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["signed_request_created"] is False
    assert report["secret_value_accessed"] is False
    assert "P10_REVIEW_ONLY_BOUNDARY_VALID_BUT_NO_LIVE_SUBMIT_PERFORMED" in report["warnings"]


def test_p10_blocks_unsafe_approval_and_intent() -> None:
    cfg = load_config()
    sources = build_valid_p10_fixture_sources()
    sources["approval_request"] = {**sources["approval_request"], "request_live_order_submission_enabled": True}
    report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P10_BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_ENABLEMENT" in report["block_reasons"]
    assert report["actual_live_order_submitted"] is False

    sources = build_valid_p10_fixture_sources()
    sources["order_intent"] = {**sources["order_intent"], "live_order_endpoint_called": True}
    report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P10_BLOCK_LIVE_ORDER_ENDPOINT_CALLED_NOT_FALSE" in report["block_reasons"]
    assert report["live_canary_execution_enabled"] is False

    sources = build_valid_p10_fixture_sources()
    sources["order_intent"] = {**sources["order_intent"], "secret_value_accessed": True}
    report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P10_BLOCK_ORDER_INTENT_SECRET_VALUE_ACCESSED_SECRET_ACCESS" in report["block_reasons"]
    assert report["secret_value_accessed"] is False


def test_p10_blocks_missing_fresh_signal_risk_idempotency_and_cap_requirements() -> None:
    cfg = load_config()
    cases = [
        ("fresh_data_snapshot", False, "P10_BLOCK_FRESH_DATA_SNAPSHOT_NOT_VALID"),
        ("signal_qa_passed", False, "P10_BLOCK_RESEARCH_SIGNAL_OR_SIGNAL_QA_NOT_VALID"),
        ("hot_path_preorder_risk_gate_fresh", False, "P10_BLOCK_HOT_PATH_PREORDER_RISK_GATE_NOT_FRESH_PASS"),
        ("idempotency_key_seen_before", True, "P10_BLOCK_DUPLICATE_IDEMPOTENCY_KEY"),
        ("post_submit_relock_planned", False, "P10_BLOCK_POST_SUBMIT_RELOCK_NOT_PLANNED"),
    ]
    for field, value, expected_blocker in cases:
        sources = build_valid_p10_fixture_sources()
        sources["order_intent"] = {**sources["order_intent"], field: value}
        if field == "fresh_data_snapshot":
            sources["order_intent"]["data_snapshot_stale"] = True
        report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg, **sources)
        assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
        assert expected_blocker in report["block_reasons"]
        assert report["actual_live_order_submitted"] is False

    sources = build_valid_p10_fixture_sources()
    sources["order_intent"] = {**sources["order_intent"], "notional_usdt": 10.0}
    report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P10_BLOCK_ORDER_INTENT_NOTIONAL_EXCEEDS_CAP" in report["block_reasons"]


def test_p10_negative_fixtures_all_block_fail_closed() -> None:
    cfg = load_config()
    negative = build_p10_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    for item in negative["fixture_results"].values():
        assert item["blocked_fail_closed"] is True
        assert item["live_canary_execution_enabled"] is False
        assert item["actual_live_order_submitted"] is False
        assert item["secret_value_accessed"] is False


def test_p10_persist_writes_latest_artifacts() -> None:
    cfg = load_config()
    report = persist_p10_live_canary_one_order_execution_boundary(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert Path("storage/latest/p10_live_canary_one_order_execution_boundary_report.json").exists()
    assert Path("storage/latest/p10_live_canary_one_order_execution_boundary_summary.json").exists()
    assert Path("storage/latest/p10_live_canary_one_order_execution_boundary_negative_fixture_results.json").exists()
    assert Path("storage/latest/p10_live_canary_one_order_execution_boundary_registry_record.json").exists()
    summary = read_json(Path("storage/latest/p10_live_canary_one_order_execution_boundary_summary.json"))
    assert summary["live_canary_execution_enabled"] is False
    assert summary["actual_live_order_submitted"] is False
    assert summary["live_order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
