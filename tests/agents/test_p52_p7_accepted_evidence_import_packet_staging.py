from __future__ import annotations

from copy import deepcopy

from crypto_ai_system.execution.p7_accepted_evidence_import_packet_staging import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_REVIEW_ONLY_NO_SUBMIT,
    STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT,
    build_p52_negative_fixture_results,
    build_p52_p7_accepted_evidence_import_packet_staging_report,
    persist_p52_p7_accepted_evidence_import_packet_staging,
    validate_p51_accepted_dry_run_source,
    validate_p52_candidate_for_staging,
    validate_staged_p7_import_packet,
)
from crypto_ai_system.execution.p7_import_bridge_dry_run import (
    _valid_candidate_fixture,
    _valid_p50_source_fixture,
    build_p51_p7_import_bridge_dry_run_report,
)


def _accepted_source_and_candidate():
    candidate = _valid_candidate_fixture()
    source = build_p51_p7_import_bridge_dry_run_report(
        p50_report=_valid_p50_source_fixture(), candidate=candidate
    )
    return source, candidate


def test_p52_default_report_is_ready_review_only_no_submit():
    report = build_p52_p7_accepted_evidence_import_packet_staging_report()
    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert report["review_only"] is True
    assert report["staging_only"] is True
    assert report["candidate_supplied"] is False
    assert report["p7_import_packet_staged"] is False
    assert report["p7_report_persisted_by_p52"] is False
    assert report["p7_valid_status_written_by_p52"] is False
    assert report["p7_intake_execution_performed_by_p52"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False


def test_p52_accepted_p51_and_matching_candidate_stage_packet_no_status_mutation():
    source, candidate = _accepted_source_and_candidate()
    report = build_p52_p7_accepted_evidence_import_packet_staging_report(p51_report=source, candidate=candidate)
    assert report["status"] == STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT
    assert report["p7_import_packet_staged"] is True
    assert report["p7_report_persisted_by_p52"] is False
    assert report["p7_valid_status_written_by_p52"] is False
    assert report["actual_order_submission_performed"] is False
    packet = report["staged_packet"]
    assert packet["artifact_type"] == "p52_p7_accepted_evidence_import_packet_STAGED_NO_SUBMIT"
    assert packet["requires_separate_operator_p7_import_action"] is True
    assert packet["cannot_be_used_as_runtime_authority"] is True
    assert packet["p7_report_persisted_by_p52"] is False
    validation = validate_staged_p7_import_packet(packet)
    assert validation["staged_packet_valid"] is True


def test_p52_blocks_candidate_hash_mismatch_against_p51_source():
    source, candidate = _accepted_source_and_candidate()
    tampered = deepcopy(candidate)
    tampered["p7_input_preview"]["client_order_id"] = "tampered_client_order"
    validation = validate_p51_accepted_dry_run_source(source, candidate=tampered, candidate_supplied=True)
    assert validation["p51_source_valid_for_staging"] is False
    assert "P52_P51_SOURCE_CANDIDATE_SHA256_MISMATCH" in validation["p51_source_block_reasons"]
    report = build_p52_p7_accepted_evidence_import_packet_staging_report(p51_report=source, candidate=tampered)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["p7_import_packet_staged"] is False


def test_p52_blocks_rejected_p51_source():
    candidate = _valid_candidate_fixture()
    candidate["p7_input_preview"]["exchange_order_id"] = "mock_order_123"
    source = build_p51_p7_import_bridge_dry_run_report(candidate=candidate)
    report = build_p52_p7_accepted_evidence_import_packet_staging_report(p51_report=source, candidate=candidate)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["p7_import_packet_staged"] is False
    assert "P52_P51_SOURCE_STATUS_NOT_ACCEPTED_REVIEW_ONLY_NO_SUBMIT" in report["block_reasons"]


def test_p52_blocks_status_mutation_attempts():
    source, candidate = _accepted_source_and_candidate()
    source = {**source, "p7_valid_status_written_by_p51": True}
    report = build_p52_p7_accepted_evidence_import_packet_staging_report(p51_report=source, candidate=candidate)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["p7_import_packet_staged"] is False
    candidate2 = {**candidate, "p7_valid_status_written_by_p52": True}
    validation = validate_p52_candidate_for_staging(candidate2)
    assert validation["candidate_valid_for_p52_staging"] is False


def test_p52_blocks_forbidden_secret_fields():
    source, candidate = _accepted_source_and_candidate()
    candidate = {**candidate, "api_secret": "redacted-but-forbidden-key"}
    report = build_p52_p7_accepted_evidence_import_packet_staging_report(p51_report=source, candidate=candidate)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["p7_import_packet_staged"] is False
    assert any("P52_FORBIDDEN_FIELD" in reason for reason in report["block_reasons"])


def test_p52_negative_fixtures_all_blocked_and_valid_fixture_stages():
    negative = build_p52_negative_fixture_results()
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["valid_candidate_fixture_stages_packet"] is True
    assert negative["p7_report_persisted_by_p52"] is False
    assert negative["p7_valid_status_written_by_p52"] is False


def test_p52_persist_writes_latest_artifacts():
    report = persist_p52_p7_accepted_evidence_import_packet_staging()
    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert report["p7_import_packet_staged"] is False
    assert report["p7_report_persisted_by_p52"] is False
    assert report["p7_valid_status_written_by_p52"] is False
