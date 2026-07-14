from __future__ import annotations

from crypto_ai_system.governance.executor_approval import (
    STATE_APPROVAL_EVIDENCE_REPAIR_REQUIRED,
    STATE_BLOCKED,
    STATE_FIXTURE_REVIEW_ONLY,
    STATE_OPERATOR_SUBMISSION_REVIEW_ONLY,
    build_executor_approval_report,
)


def _safe_base(
    *,
    id_field: str,
    id_value: str,
    hash_field: str,
    status: str,
) -> dict:
    return {
        id_field: id_value,
        hash_field: "a" * 64,
        "status": status,
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "runtime_permission_source": False,
        "executor_approval_runtime_authority": False,
        "executor_approval_authority": False,
        "executor_enablement_authority": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
    }


def _ready_outputs(
    *,
    actual_operator_submission: bool = False,
) -> dict:
    prerequisite = _safe_base(
        id_field=(
            "phase7_7_future_executor_review_"
            "prerequisite_design_id"
        ),
        id_value="prerequisite_1",
        hash_field="phase7_7_report_sha256",
        status=(
            "PHASE7_7_FUTURE_EXECUTOR_REVIEW_"
            "PREREQUISITE_DESIGN_RECORDED_REVIEW_ONLY"
        ),
    )

    prerequisite.update(
        {
            "phase7_7_prerequisite_design_ready": True,
            "future_executor_prerequisite_guard_passed": True,
            "future_executor_review_prerequisites_ready_review_only": True,
            "future_executor_review_required_before_any_order": True,
        }
    )

    template = _safe_base(
        id_field=(
            "phase7_8_future_executor_approval_"
            "packet_template_id"
        ),
        id_value="template_1",
        hash_field="phase7_8_report_sha256",
        status=(
            "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_"
            "TEMPLATE_RECORDED_REVIEW_ONLY"
        ),
    )

    template.update(
        {
            "phase7_8_template_ready": True,
            "future_executor_approval_template_created": True,
            "template_guard_passed": True,
            "executor_approval_template_operator_required_fields": [
                "operator_id",
                "operator_ticket_or_signature",
            ],
        }
    )

    intake = _safe_base(
        id_field=(
            "phase7_9_future_executor_approval_"
            "intake_validator_id"
        ),
        id_value="intake_1",
        hash_field="phase7_9_report_sha256",
        status=(
            "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_"
            "VALIDATOR_RECORDED_REVIEW_ONLY"
        ),
    )

    intake.update(
        {
            "phase7_9_intake_validation_ready": True,
            "intake_guard_passed": True,
            "actual_operator_submission_present": (
                actual_operator_submission
            ),
            "validated_submission_source": (
                "actual_operator_submission"
                if actual_operator_submission
                else "valid_review_only_fixture"
            ),
            "valid_future_executor_approval_submission_"
            "passed_review_only_validation": True,
            "invalid_future_executor_approval_submission_"
            "fixtures_blocked_fail_closed": True,
            "metadata_only_key_reference_validated_review_only": True,
        }
    )

    review = _safe_base(
        id_field=(
            "phase7_10_future_executor_approval_"
            "review_packet_id"
        ),
        id_value="review_1",
        hash_field="phase7_10_report_sha256",
        status=(
            "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_"
            "REVIEW_PACKET_RECORDED_REVIEW_ONLY"
        ),
    )

    review.update(
        {
            "phase7_10_review_packet_ready": True,
            "review_guard_passed": True,
            "phase7_9_intake_validation_ready": True,
            "future_executor_approval_intake_"
            "validation_record_valid": True,
            "future_executor_approval_intake_"
            "guard_passed": True,
            "metadata_only_key_reference_"
            "validated_review_only": True,
            "prerequisite_packet_hash_matches": True,
            "hard_caps_numeric": True,
            "fresh_rechecks_true": True,
        }
    )

    return {
        "future_executor_prerequisite_design": prerequisite,
        "future_executor_approval_template": template,
        "future_executor_approval_intake": intake,
        "future_executor_approval_review_packet": review,
    }


def test_fixture_path_is_explicitly_non_authoritative() -> None:
    report = build_executor_approval_report(
        legacy_outputs=_ready_outputs(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["executor_approval_review_state"]
        == STATE_FIXTURE_REVIEW_ONLY
    )

    assert report["blocked"] is False

    assert (
        report["actual_operator_submission_present"]
        is False
    )

    assert (
        report["validated_submission_source"]
        == "valid_review_only_fixture"
    )

    assert (
        report["fixture_validation_only"]
        is True
    )

    assert (
        report["fixture_validation_is_executor_approval"]
        is False
    )

    assert (
        report["executor_approval_runtime_authority"]
        is False
    )

    assert (
        report["actual_executor_approval_created"]
        is False
    )

    assert (
        report["ready_for_signed_testnet_execution"]
        is False
    )

    assert (
        report["testnet_order_submission_allowed"]
        is False
    )

    assert (
        report["signed_order_executor_enabled"]
        is False
    )


def test_actual_operator_submission_stays_review_only() -> None:
    report = build_executor_approval_report(
        legacy_outputs=_ready_outputs(
            actual_operator_submission=True,
        ),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["executor_approval_review_state"]
        == STATE_OPERATOR_SUBMISSION_REVIEW_ONLY
    )

    assert report["blocked"] is False

    assert (
        report["actual_operator_submission_present"]
        is True
    )

    assert (
        report["validated_submission_source"]
        == "actual_operator_submission"
    )

    assert (
        report[
            "operator_submission_validation_is_runtime_authority"
        ]
        is False
    )

    assert (
        report["actual_executor_approval_created"]
        is False
    )

    assert (
        report["testnet_order_submission_allowed"]
        is False
    )


def test_intake_evidence_failure_requires_repair() -> None:
    outputs = _ready_outputs()

    intake = outputs[
        "future_executor_approval_intake"
    ]

    intake[
        "phase7_9_intake_validation_ready"
    ] = False

    intake[
        "intake_guard_passed"
    ] = False

    intake[
        "blocked"
    ] = True

    intake[
        "fail_closed"
    ] = True

    report = build_executor_approval_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["executor_approval_review_state"]
        == STATE_APPROVAL_EVIDENCE_REPAIR_REQUIRED
    )

    assert report["blocked"] is True
    assert report["fail_closed"] is True

    assert (
        "FUTURE_EXECUTOR_APPROVAL_INTAKE_NOT_READY"
        in report["blockers"]
    )

    assert (
        report["testnet_order_submission_allowed"]
        is False
    )


def test_actual_approval_flag_is_exposed_and_blocked() -> None:
    outputs = _ready_outputs()

    outputs[
        "future_executor_approval_review_packet"
    ][
        "actual_executor_approval_created"
    ] = True

    report = build_executor_approval_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["executor_approval_review_state"]
        == STATE_BLOCKED
    )

    assert report["blocked"] is True

    assert (
        report[
            "source_actual_executor_approval_created"
        ]
        is True
    )

    assert (
        report["actual_executor_approval_created"]
        is True
    )

    assert (
        "ACTUAL_EXECUTOR_APPROVAL_CREATED_UNEXPECTEDLY"
        in report["blockers"]
    )

    assert (
        report["executor_approval_runtime_authority"]
        is False
    )

    assert (
        report["external_order_submission_allowed"]
        is False
    )


def test_unsafe_submission_permission_does_not_propagate() -> None:
    outputs = _ready_outputs()

    outputs[
        "future_executor_approval_intake"
    ][
        "testnet_order_submission_allowed"
    ] = True

    report = build_executor_approval_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["executor_approval_review_state"]
        == STATE_BLOCKED
    )

    assert report["blocked"] is True

    assert (
        "EXECUTOR_APPROVAL_COMPONENT_UNSAFE_FLAG:"
        "future_executor_approval_intake"
        in report["blockers"]
    )

    assert (
        report["testnet_order_submission_allowed"]
        is False
    )

    assert (
        report["place_order_enabled"]
        is False
    )
