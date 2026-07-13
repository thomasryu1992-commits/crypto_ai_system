from __future__ import annotations

from crypto_ai_system.governance.approval import (
    STATE_BLOCKED,
    STATE_SUBMITTED_REVIEW_ONLY,
    STATE_WAITING_FOR_HUMAN,
    build_approval_review_report,
)


def _intake_waiting() -> dict:
    return {
        "phase5_manual_approval_intake_validation_id": "phase5_intake_1",
        "phase5_report_sha256": "a" * 64,
        "status": "PHASE5_MANUAL_APPROVAL_INTAKE_BLOCKED_REVIEW_ONLY",
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "manual_approval_submission_present": False,
        "block_reasons": ["MANUAL_APPROVAL_SUBMISSION_MISSING"],
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
    }


def _handoff_ready() -> dict:
    return {
        "phase5_1_manual_approval_operator_handoff_id": "handoff_1",
        "phase5_1_report_sha256": "b" * 64,
        "status": "PHASE5_1_MANUAL_APPROVAL_OPERATOR_HANDOFF_RECORDED_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "manual_approval_submission_template_created": True,
        "manual_approval_submission_created": False,
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
    }


def _fixtures_ready() -> dict:
    return {
        "phase5_2_manual_approval_submission_fixture_validator_id": "fixtures_1",
        "phase5_2_report_sha256": "c" * 64,
        "status": "PHASE5_2_MANUAL_APPROVAL_SUBMISSION_FIXTURE_VALIDATOR_RECORDED_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "valid_fixture_passed_review_only_validation": True,
        "invalid_fixtures_blocked_fail_closed": True,
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
    }


def test_missing_manual_submission_is_expected_waiting_not_runtime_failure() -> None:
    report = build_approval_review_report(
        intake_validation=_intake_waiting(),
        operator_handoff=_handoff_ready(),
        fixture_validation=_fixtures_ready(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["approval_state"] == STATE_WAITING_FOR_HUMAN
    assert report["blocked"] is False
    assert report["intake_waiting_state_expected"] is True
    assert report["manual_approval_submission_present"] is False
    assert report["runtime_permission_source"] is False
    assert report["approval_intake_validated"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_allowed"] is False


def test_submission_presence_remains_review_only_not_runtime_authority() -> None:
    intake = _intake_waiting()
    intake.update(
        {
            "status": "PHASE5_MANUAL_APPROVAL_INTAKE_VALIDATION_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "fail_closed": False,
            "manual_approval_submission_present": True,
            "block_reasons": [],
        }
    )

    report = build_approval_review_report(
        intake_validation=intake,
        operator_handoff=_handoff_ready(),
        fixture_validation=_fixtures_ready(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["approval_state"] == STATE_SUBMITTED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["approval_intake_validated"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_structural_intake_failure_blocks_fail_closed() -> None:
    intake = _intake_waiting()
    intake["block_reasons"] = [
        "MANUAL_APPROVAL_SUBMISSION_MISSING",
        "APPROVAL_PACKET_DRAFT_HASH_INVALID",
    ]

    report = build_approval_review_report(
        intake_validation=intake,
        operator_handoff=_handoff_ready(),
        fixture_validation=_fixtures_ready(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["approval_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert "APPROVAL_COMPONENT_BLOCKED:intake_validation" in report["blockers"]


def test_unsafe_component_flag_blocks_without_propagating_permission() -> None:
    handoff = _handoff_ready()
    handoff["auto_promotion_allowed"] = True

    report = build_approval_review_report(
        intake_validation=_intake_waiting(),
        operator_handoff=handoff,
        fixture_validation=_fixtures_ready(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["approval_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert "APPROVAL_COMPONENT_UNSAFE_FLAG:operator_handoff" in report["blockers"]
    assert report["auto_promotion_allowed"] is False
    assert report["testnet_order_submission_allowed"] is False
