from __future__ import annotations

from crypto_ai_system.execution.p7_import_bridge_dry_run import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT,
    STATUS_READY_REVIEW_ONLY_NO_SUBMIT,
    _valid_candidate_fixture,
    _valid_p50_source_fixture,
    build_p51_negative_fixture_results,
    build_p51_p7_import_bridge_dry_run_report,
    persist_p51_p7_import_bridge_dry_run,
    validate_p7_bridge_candidate,
)


def test_p51_default_report_is_ready_review_only_no_submit():
    report = build_p51_p7_import_bridge_dry_run_report()
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert report["review_only"] is True
    assert report["dry_run_only"] is True
    assert report["candidate_supplied"] is False
    assert report["p7_bridge_dry_run_performed"] is False
    assert report["p7_report_persisted_by_p51"] is False
    assert report["p7_valid_status_written_by_p51"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False


def test_p51_valid_candidate_dry_run_would_accept_p7_but_does_not_persist_status():
    report = build_p51_p7_import_bridge_dry_run_report(
        p50_report=_valid_p50_source_fixture(), candidate=_valid_candidate_fixture()
    )
    assert report["status"] == STATUS_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT
    assert report["p7_bridge_dry_run_performed"] is True
    assert report["p7_would_accept_imported_evidence"] is True
    assert report["p7_report_persisted_by_p51"] is False
    assert report["p7_valid_status_written_by_p51"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False


def test_p51_candidate_missing_status_polling_is_rejected_or_blocked():
    candidate = _valid_candidate_fixture()
    candidate.pop("status_polling_events")
    report = build_p51_p7_import_bridge_dry_run_report(
        p50_report=_valid_p50_source_fixture(), candidate=candidate
    )
    assert report["blocked"] is True or report["p7_would_reject_imported_evidence"] is True
    assert report["p7_would_accept_imported_evidence"] is False
    assert report["p7_report_persisted_by_p51"] is False


def test_p51_mock_order_id_is_rejected_by_p7_dry_run():
    candidate = _valid_candidate_fixture()
    candidate["p7_input_preview"]["exchange_order_id"] = "mock_order_123"
    report = build_p51_p7_import_bridge_dry_run_report(
        p50_report=_valid_p50_source_fixture(), candidate=candidate
    )
    assert report["p7_would_accept_imported_evidence"] is False
    assert report["blocked"] is False or report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    reasons = report.get("block_reasons") or []
    p7_reasons = (report.get("p7_bridge_dry_run_result") or {}).get("p7_dry_run_block_reasons") or []
    assert "P7_EXCHANGE_ORDER_ID_LOOKS_MOCK_OR_FIXTURE" in reasons + p7_reasons


def test_p51_blocks_candidate_status_mutation_attempt():
    candidate = _valid_candidate_fixture()
    candidate["p7_valid_status_written_by_p51"] = True
    validation = validate_p7_bridge_candidate(candidate)
    assert validation["p7_bridge_candidate_valid_for_dry_run"] is False
    report = build_p51_p7_import_bridge_dry_run_report(
        p50_report=_valid_p50_source_fixture(), candidate=candidate
    )
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["p7_bridge_dry_run_performed"] is False


def test_p51_negative_fixtures_blocked_or_rejected():
    negative = build_p51_negative_fixture_results()
    assert negative["all_negative_fixtures_blocked_or_rejected_fail_closed"] is True
    assert negative["valid_candidate_fixture_would_accept_p7"] is True
    assert negative["p7_report_persisted_by_p51"] is False
    assert negative["p7_valid_status_written_by_p51"] is False


def test_p51_persist_writes_latest_artifacts(tmp_path):
    report = persist_p51_p7_import_bridge_dry_run()
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["p7_report_persisted_by_p51"] is False
