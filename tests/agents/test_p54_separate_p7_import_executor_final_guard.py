from __future__ import annotations

from copy import deepcopy

from crypto_ai_system.execution.separate_p7_import_executor_final_guard import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED,
    STATUS_READY_REVIEW_ONLY_EXECUTOR_DISABLED,
    build_p54_negative_fixture_results,
    build_p54_separate_p7_import_executor_final_guard_report,
    build_valid_p54_guard_inputs_fixture,
    persist_p54_separate_p7_import_executor_final_guard,
    validate_append_only_registry_policy_evidence,
    validate_duplicate_import_lock_evidence,
    validate_final_guard_passed_packet,
    validate_no_secret_evidence_attestation,
    validate_nonce_freshness_evidence,
    validate_p52_source_and_candidate_chain,
    validate_p53_armed_source,
)
from crypto_ai_system.utils.audit import sha256_json


def _rehash(payload: dict, key: str) -> None:
    payload[key] = sha256_json({k: v for k, v in payload.items() if k != key})


def test_p54_default_report_is_ready_review_only_executor_disabled():
    report = build_p54_separate_p7_import_executor_final_guard_report()
    assert report["status"] == STATUS_READY_REVIEW_ONLY_EXECUTOR_DISABLED
    assert report["review_only"] is True
    assert report["final_guard_only"] is True
    assert report["executor_disabled_by_default"] is True
    assert report["final_guard_evaluation_requested"] is False
    assert report["final_guard_passed"] is False
    assert report["p7_import_executor_enabled"] is False
    assert report["p7_import_executor_action_allowed"] is False
    assert report["p7_import_executor_action_executed"] is False
    assert report["p7_report_persisted_by_p54"] is False
    assert report["p7_valid_status_written_by_p54"] is False
    assert report["p7_registry_append_performed_by_p54"] is False
    assert report["p7_import_action_nonce_consumed_by_p54"] is False
    assert report["p7_duplicate_import_lock_acquired_by_p54"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False


def test_p54_valid_inputs_pass_guard_but_keep_executor_disabled():
    inputs = build_valid_p54_guard_inputs_fixture()
    report = build_p54_separate_p7_import_executor_final_guard_report(**inputs)
    assert report["status"] == STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED
    assert report["final_guard_passed"] is True
    assert report["p7_import_executor_enabled"] is False
    assert report["p7_import_executor_action_allowed"] is False
    assert report["p7_import_executor_action_executed"] is False
    assert report["p7_report_persisted_by_p54"] is False
    assert report["p7_valid_status_written_by_p54"] is False
    assert report["p7_registry_append_performed_by_p54"] is False
    assert report["p7_import_action_nonce_consumed_by_p54"] is False
    assert report["p7_duplicate_import_lock_acquired_by_p54"] is False
    packet = report["final_guard_packet"]
    assert packet["final_guard_passed"] is True
    assert packet["executor_disabled"] is True
    assert packet["p7_import_executor_enabled"] is False
    assert packet["requires_atomic_duplicate_lock_acquisition"] is True
    assert packet["requires_atomic_nonce_consume_and_append_only_registry_write"] is True
    validation = validate_final_guard_passed_packet(packet)
    assert validation["final_guard_passed_packet_valid"] is True


def test_p54_revalidates_p53_and_p52_embedded_hash_chain():
    inputs = build_valid_p54_guard_inputs_fixture()
    p53_validation = validate_p53_armed_source(
        inputs["p53_report"],
        p52_report=inputs["p52_report"],
    )
    assert p53_validation["p53_source_valid_for_p54"] is True
    p52_validation = validate_p52_source_and_candidate_chain(
        inputs["p52_report"],
        candidate=inputs["candidate"],
        p53_report=inputs["p53_report"],
    )
    assert p52_validation["p52_source_and_candidate_chain_valid"] is True
    assert p52_validation["all_candidate_section_hashes_match"] is True


def test_p54_blocks_p53_report_hash_tampering():
    inputs = build_valid_p54_guard_inputs_fixture()
    bad = deepcopy(inputs)
    bad["p53_report"]["p53_operator_controlled_p7_import_action_boundary_sha256"] = "f" * 64
    report = build_p54_separate_p7_import_executor_final_guard_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["final_guard_passed"] is False
    assert "P54_P53_SOURCE_EMBEDDED_SHA256_INVALID" in report["block_reasons"]


def test_p54_blocks_candidate_or_section_hash_mismatch():
    inputs = build_valid_p54_guard_inputs_fixture()
    bad = deepcopy(inputs)
    bad["candidate"]["p7_input_preview"]["client_order_id"] = "mutated_client_order_id"
    report = build_p54_separate_p7_import_executor_final_guard_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("CANDIDATE_SHA256_MISMATCH" in reason for reason in report["block_reasons"])
    assert any("CANDIDATE_SECTION_SHA256_MISMATCH" in reason for reason in report["block_reasons"])


def test_p54_nonce_freshness_evidence_requires_unseen_unconsumed_fresh_nonce():
    inputs = build_valid_p54_guard_inputs_fixture()
    valid = validate_nonce_freshness_evidence(
        inputs["nonce_freshness_evidence"],
        p53_report=inputs["p53_report"],
    )
    assert valid["nonce_freshness_evidence_valid"] is True

    bad = deepcopy(inputs)
    bad["nonce_freshness_evidence"]["nonce_seen_before"] = True
    _rehash(bad["nonce_freshness_evidence"], "p54_nonce_freshness_evidence_sha256")
    report = build_p54_separate_p7_import_executor_final_guard_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("NONCE_SEEN_BEFORE" in reason for reason in report["block_reasons"])


def test_p54_duplicate_lock_evidence_requires_no_duplicate_and_no_lock_acquisition_by_p54():
    inputs = build_valid_p54_guard_inputs_fixture()
    valid = validate_duplicate_import_lock_evidence(
        inputs["duplicate_import_lock_evidence"],
        p52_report=inputs["p52_report"],
    )
    assert valid["duplicate_import_lock_evidence_valid"] is True
    assert valid["duplicate_import_lock_ready"] is True
    assert valid["duplicate_import_lock_acquired"] is False

    bad = deepcopy(inputs)
    bad["duplicate_import_lock_evidence"]["duplicate_import_detected"] = True
    bad["duplicate_import_lock_evidence"]["existing_import_record_count"] = 1
    _rehash(bad["duplicate_import_lock_evidence"], "p54_duplicate_import_lock_evidence_sha256")
    report = build_p54_separate_p7_import_executor_final_guard_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("DUPLICATE_IMPORT_DETECTED" in reason for reason in report["block_reasons"])


def test_p54_no_secret_attestation_requires_clean_scan_and_redacted_only():
    inputs = build_valid_p54_guard_inputs_fixture()
    valid = validate_no_secret_evidence_attestation(
        inputs["no_secret_evidence_attestation"],
        p52_report=inputs["p52_report"],
        candidate=inputs["candidate"],
    )
    assert valid["no_secret_evidence_attestation_valid"] is True
    assert valid["no_secret_scan_passed"] is True
    assert valid["no_secret_scan_match_count"] == 0

    bad = deepcopy(inputs)
    bad["no_secret_evidence_attestation"]["api_secret_value_included"] = True
    _rehash(bad["no_secret_evidence_attestation"], "p54_no_secret_evidence_attestation_sha256")
    report = build_p54_separate_p7_import_executor_final_guard_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("API_SECRET_VALUE_INCLUDED" in reason for reason in report["block_reasons"])


def test_p54_registry_policy_is_append_only_and_p54_cannot_write():
    inputs = build_valid_p54_guard_inputs_fixture()
    valid = validate_append_only_registry_policy_evidence(inputs["append_only_registry_policy_evidence"])
    assert valid["append_only_registry_policy_evidence_valid"] is True
    assert valid["append_only"] is True
    assert valid["registry_append_performed_by_p54"] is False

    bad = deepcopy(inputs)
    bad["append_only_registry_policy_evidence"]["overwrite_allowed"] = True
    _rehash(
        bad["append_only_registry_policy_evidence"],
        "p54_append_only_p7_registry_policy_evidence_sha256",
    )
    report = build_p54_separate_p7_import_executor_final_guard_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P54_REGISTRY_POLICY_OVERWRITE_ALLOWED_NOT_FALSE" in report["block_reasons"]


def test_p54_negative_fixtures_all_fail_closed_and_valid_fixture_passes_disabled():
    negative = build_p54_negative_fixture_results()
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["valid_fixture_final_guard_passed_executor_disabled"] is True
    assert negative["p7_import_executor_enabled"] is False
    assert negative["p7_import_executor_action_executed"] is False
    assert negative["p7_report_persisted_by_p54"] is False
    assert negative["p7_valid_status_written_by_p54"] is False


def test_p54_persist_writes_default_executor_disabled_artifacts():
    report = persist_p54_separate_p7_import_executor_final_guard()
    assert report["status"] == STATUS_READY_REVIEW_ONLY_EXECUTOR_DISABLED
    assert report["final_guard_evaluation_requested"] is False
    assert report["final_guard_passed"] is False
    assert report["p7_import_executor_enabled"] is False
    assert report["p7_import_executor_action_executed"] is False
    assert report["p7_report_persisted_by_p54"] is False
