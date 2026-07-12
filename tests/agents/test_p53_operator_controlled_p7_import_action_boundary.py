from __future__ import annotations

from copy import deepcopy

from crypto_ai_system.execution.operator_controlled_p7_import_action_boundary import (
    STATUS_ARMED_REVIEW_ONLY_NO_IMPORT,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_REVIEW_ONLY_NO_IMPORT,
    build_p53_negative_fixture_results,
    build_p53_operator_controlled_p7_import_action_boundary_report,
    build_valid_operator_request_fixture,
    persist_p53_operator_controlled_p7_import_action_boundary,
    validate_armed_boundary_packet,
    validate_operator_request,
)
from crypto_ai_system.execution.p7_accepted_evidence_import_packet_staging import (
    _valid_candidate_fixture,
    build_p52_p7_accepted_evidence_import_packet_staging_report,
)
from crypto_ai_system.execution.p7_import_bridge_dry_run import build_p51_p7_import_bridge_dry_run_report


def _valid_p52_and_request():
    candidate = _valid_candidate_fixture()
    p51 = build_p51_p7_import_bridge_dry_run_report(candidate=candidate)
    p52 = build_p52_p7_accepted_evidence_import_packet_staging_report(p51_report=p51, candidate=candidate)
    request = build_valid_operator_request_fixture(p52)
    return p52, request


def test_p53_default_report_is_ready_review_only_no_import():
    report = build_p53_operator_controlled_p7_import_action_boundary_report()
    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_IMPORT
    assert report["review_only"] is True
    assert report["operator_controlled"] is True
    assert report["operator_request_supplied"] is False
    assert report["p7_import_action_boundary_armed"] is False
    assert report["p7_import_action_enabled"] is False
    assert report["p7_import_action_executed"] is False
    assert report["p7_report_persisted_by_p53"] is False
    assert report["p7_valid_status_written_by_p53"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False


def test_p53_valid_operator_request_arms_boundary_but_does_not_import():
    p52, request = _valid_p52_and_request()
    report = build_p53_operator_controlled_p7_import_action_boundary_report(
        p52_report=p52,
        operator_request=request,
    )
    assert report["status"] == STATUS_ARMED_REVIEW_ONLY_NO_IMPORT
    assert report["p7_import_action_boundary_armed"] is True
    assert report["p7_import_action_enabled"] is False
    assert report["p7_import_action_executed"] is False
    assert report["p7_report_persisted_by_p53"] is False
    assert report["p7_valid_status_written_by_p53"] is False
    packet = report["armed_boundary_packet"]
    assert packet["requires_separate_p7_import_executor"] is True
    assert packet["requires_fresh_revalidation_at_import_time"] is True
    assert packet["p7_import_action_enabled"] is False
    validation = validate_armed_boundary_packet(packet)
    assert validation["armed_boundary_packet_valid"] is True


def test_p53_blocks_wrong_exact_phrase():
    p52, request = _valid_p52_and_request()
    bad = deepcopy(request)
    bad["exact_operator_authorization_phrase"] = "AUTHORIZE IMPORT"
    validation = validate_operator_request(bad, p52_report=p52)
    assert validation["operator_request_valid_for_arming"] is False
    assert "P53_OPERATOR_REQUEST_EXACT_PHRASE_INVALID" in validation["operator_request_block_reasons"]
    report = build_p53_operator_controlled_p7_import_action_boundary_report(p52_report=p52, operator_request=bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["p7_import_action_boundary_armed"] is False


def test_p53_blocks_staged_packet_hash_mismatch():
    p52, request = _valid_p52_and_request()
    bad = deepcopy(request)
    bad["source_p52_staged_packet_sha256"] = "f" * 64
    report = build_p53_operator_controlled_p7_import_action_boundary_report(p52_report=p52, operator_request=bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("STAGED_PACKET_SHA256_MISMATCH" in reason for reason in report["block_reasons"])


def test_p53_blocks_runtime_authority_and_import_execution_attempts():
    p52, request = _valid_p52_and_request()
    runtime = deepcopy(request)
    runtime["runtime_authority_requested"] = True
    report = build_p53_operator_controlled_p7_import_action_boundary_report(p52_report=p52, operator_request=runtime)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    execute = deepcopy(request)
    execute["p7_import_execution_allowed_by_p53"] = True
    report2 = build_p53_operator_controlled_p7_import_action_boundary_report(p52_report=p52, operator_request=execute)
    assert report2["status"] == STATUS_BLOCKED_FAIL_CLOSED


def test_p53_blocks_secret_field_and_mainnet_scope():
    p52, request = _valid_p52_and_request()
    secret = deepcopy(request)
    secret["api_secret"] = "forbidden"
    report = build_p53_operator_controlled_p7_import_action_boundary_report(p52_report=p52, operator_request=secret)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("P53_FORBIDDEN_FIELD" in reason for reason in report["block_reasons"])
    mainnet = deepcopy(request)
    mainnet["environment"] = "mainnet"
    report2 = build_p53_operator_controlled_p7_import_action_boundary_report(p52_report=p52, operator_request=mainnet)
    assert report2["status"] == STATUS_BLOCKED_FAIL_CLOSED


def test_p53_negative_fixtures_all_blocked_and_valid_fixture_arms_no_import():
    negative = build_p53_negative_fixture_results()
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["valid_fixture_arms_boundary_no_import"] is True
    assert negative["p7_import_action_executed"] is False
    assert negative["p7_report_persisted_by_p53"] is False
    assert negative["p7_valid_status_written_by_p53"] is False


def test_p53_persist_writes_default_no_import_artifacts():
    report = persist_p53_operator_controlled_p7_import_action_boundary()
    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_IMPORT
    assert report["p7_import_action_boundary_armed"] is False
    assert report["p7_import_action_executed"] is False
    assert report["p7_report_persisted_by_p53"] is False
