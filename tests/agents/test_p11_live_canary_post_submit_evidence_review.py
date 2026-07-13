from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_canary_post_submit_evidence_review import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    LiveCanaryCancelBoundaryEvidence,
    LiveCanaryOutcomeReviewEvidence,
    LiveCanaryReconciliationEvidence,
    LiveCanaryStatusPollingEvidence,
    build_p11_live_canary_post_submit_evidence_review_report,
    build_p11_negative_fixture_results,
    build_valid_p11_fixture_sources,
    persist_p11_live_canary_post_submit_evidence_review,
)


def test_p11_latest_waits_when_external_live_submit_evidence_missing() -> None:
    cfg = load_config()
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["external_live_canary_submit_evidence_present"] is False
    assert report["live_canary_post_submit_chain_complete"] is False
    assert report["live_canary_reconciliation_clean"] is False
    assert report["canary_outcome_review_completed"] is False
    assert report["post_submit_relock_confirmed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["actual_live_order_submitted"] is False
    assert report["live_order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p11_valid_fixture_records_clean_outcome_review_without_live_scaled_promotion() -> None:
    cfg = load_config()
    sources = build_valid_p11_fixture_sources()
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg, **sources)

    assert report["status"] == STATUS_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["external_live_canary_submit_evidence_present"] is True
    assert report["live_canary_post_submit_chain_complete"] is True
    assert report["live_canary_reconciliation_clean"] is True
    assert report["canary_outcome_review_completed"] is True
    assert report["post_submit_relock_confirmed"] is True
    assert report["live_canary_order_evidence_exists"] is True
    assert report["live_canary_order_count"] == 1
    assert report["live_canary_no_unintended_second_order"] is True
    assert report["live_canary_slippage_latency_api_error_within_threshold"] is True
    assert report["live_canary_secret_leak_absent"] is True
    assert report["live_scaled_readiness_candidate_created"] is False
    assert report["live_scaled_readiness_allowed"] is False
    assert report["live_scaled_promotion_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["secret_value_accessed"] is False
    assert report["secret_value_logged"] is False
    assert report["actual_live_order_submitted"] is True
    assert report["live_order_endpoint_called"] is True
    assert report["order_status_endpoint_called"] is True
    assert report["unsafe_truthy_execution_flags"] == []


def test_p11_blocks_mismatch_secret_leak_and_live_scaled_promotion() -> None:
    cfg = load_config()

    sources = build_valid_p11_fixture_sources()
    sources["reconciliation_evidence"] = {**sources["reconciliation_evidence"].to_dict(), "reconciliation_mismatch_count": 1}
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P11_RECONCILIATION_MISMATCH_COUNT_NONZERO" in report["block_reasons"]
    assert report["live_scaled_execution_enabled"] is False

    sources = build_valid_p11_fixture_sources()
    sources["status_polling_events"] = [{**LiveCanaryStatusPollingEvidence().to_dict(), "secret_value_logged": True}]
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P11_STATUS_EVENT_0_SECRET_VALUE_LOGGED" in report["block_reasons"]
    assert report["secret_value_accessed"] is False

    sources = build_valid_p11_fixture_sources()
    sources["outcome_review_evidence"] = {**sources["outcome_review_evidence"].to_dict(), "live_scaled_promotion_allowed": True}
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P11_LIVE_SCALED_PROMOTION_ALLOWED_TOO_EARLY" in report["block_reasons"]
    assert report["live_scaled_execution_enabled"] is False


def test_p11_blocks_open_status_without_cancel_request() -> None:
    cfg = load_config()
    sources = build_valid_p11_fixture_sources()
    sources["status_polling_events"] = [{**LiveCanaryStatusPollingEvidence().to_dict(), "exchange_order_status": "NEW"}]
    sources["cancel_boundary"] = {
        **LiveCanaryCancelBoundaryEvidence().to_dict(),
        "final_status_before_cancel_decision": "NEW",
        "cancel_required": True,
        "cancel_requested": False,
    }
    sources["reconciliation_evidence"] = {
        **LiveCanaryReconciliationEvidence().to_dict(),
        "final_exchange_order_status": "NEW",
    }
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P11_CANCEL_REQUIRED_BUT_NOT_REQUESTED" in report["block_reasons"]


def test_p11_blocks_outcome_without_post_submit_relock() -> None:
    cfg = load_config()
    sources = build_valid_p11_fixture_sources()
    sources["outcome_review_evidence"] = {**LiveCanaryOutcomeReviewEvidence().to_dict(), "post_submit_relock_confirmed": False}
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg, **sources)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P11_POST_SUBMIT_RELOCK_NOT_CONFIRMED" in report["block_reasons"]


def test_p11_negative_fixtures_all_block_fail_closed() -> None:
    cfg = load_config()
    negative = build_p11_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    for item in negative["fixture_results"].values():
        assert item["blocked_fail_closed"] is True
        assert item["live_scaled_execution_enabled"] is False
        assert item["live_scaled_promotion_allowed"] is False
        assert item["secret_value_accessed"] is False


def test_p11_persist_writes_latest_artifacts() -> None:
    cfg = load_config()
    report = persist_p11_live_canary_post_submit_evidence_review(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert Path("storage/latest/p11_live_canary_post_submit_evidence_review_report.json").exists()
    assert Path("storage/latest/p11_live_canary_post_submit_evidence_review_summary.json").exists()
    assert Path("storage/latest/p11_live_canary_post_submit_evidence_review_negative_fixture_results.json").exists()
    assert Path("storage/latest/p11_live_canary_post_submit_evidence_review_registry_record.json").exists()
    summary = read_json(Path("storage/latest/p11_live_canary_post_submit_evidence_review_summary.json"))
    assert summary["external_live_canary_submit_evidence_present"] is False
    assert summary["live_canary_post_submit_chain_complete"] is False
    assert summary["live_canary_execution_enabled"] is False
    assert summary["live_scaled_execution_enabled"] is False
    assert summary["live_scaled_promotion_allowed"] is False
    assert summary["secret_value_accessed"] is False
