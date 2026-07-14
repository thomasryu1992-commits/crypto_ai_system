from __future__ import annotations

from crypto_ai_system.governance.stage_transition import (
    STATE_BLOCKED,
    STATE_OPERATOR_DECISION_PACKET_REVIEW_ONLY,
    STATE_STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED,
    build_stage_transition_review_report,
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
        "operator_decision_runtime_authority": False,
        "stage_transition_authority": False,
        "executor_enablement_authority": False,
        "executor_approval_authority": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "actual_operator_decision_recorded": False,
        "actual_stage_transition_performed": False,
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
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
    }


def _ready_outputs() -> dict:
    design = _safe_base(
        id_field=(
            "phase7_11_future_executor_enablement_"
            "design_review_id"
        ),
        id_value="design_1",
        hash_field="phase7_11_report_sha256",
        status=(
            "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_"
            "DESIGN_REVIEW_RECORDED_REVIEW_ONLY"
        ),
    )

    design.update(
        {
            "phase7_11_enablement_design_ready": True,
            "future_executor_enablement_design_packet_created": True,
            "future_executor_enablement_design_guard_created": True,
            "enablement_design_guard_passed": True,
            "phase7_10_review_packet_ready": True,
            "approval_review_guard_passed": True,
            "metadata_only_key_reference_"
            "validated_review_only": True,
            "prerequisite_packet_hash_matches": True,
            "future_executor_approval_intake_"
            "validated_review_only": True,
            "future_explicit_executor_"
            "enablement_review_required": True,
        }
    )

    fixture = _safe_base(
        id_field=(
            "phase7_12_future_executor_enablement_"
            "guard_fixture_id"
        ),
        id_value="fixture_1",
        hash_field="phase7_12_report_sha256",
        status=(
            "PHASE7_12_FUTURE_EXECUTOR_ENABLEMENT_"
            "GUARD_FIXTURE_RECORDED_REVIEW_ONLY"
        ),
    )

    fixture.update(
        {
            "phase7_12_guard_fixture_ready": True,
            "valid_enablement_guard_fixture_"
            "passed_review_only_validation": True,
            "invalid_enablement_guard_fixtures_"
            "blocked_fail_closed": True,
            "enablement_guard_fixture_guard_passed": True,
        }
    )

    review = _safe_base(
        id_field=(
            "phase7_13_future_executor_enablement_"
            "review_packet_id"
        ),
        id_value="review_1",
        hash_field="phase7_13_report_sha256",
        status=(
            "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_"
            "REVIEW_PACKET_RECORDED_REVIEW_ONLY"
        ),
    )

    review.update(
        {
            "phase7_13_review_packet_ready": True,
            "future_executor_enablement_"
            "review_packet_created": True,
            "future_executor_enablement_"
            "review_guard_report_created": True,
            "enablement_review_guard_passed": True,
            "future_executor_enablement_review_"
            "required_before_any_order": True,
        }
    )

    decision = _safe_base(
        id_field=(
            "phase7_14_future_executor_operator_"
            "decision_packet_id"
        ),
        id_value="decision_1",
        hash_field="phase7_14_report_sha256",
        status=(
            "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_"
            "DECISION_PACKET_RECORDED_REVIEW_ONLY"
        ),
    )

    decision.update(
        {
            "phase7_14_operator_decision_packet_ready": True,
            "future_executor_operator_"
            "decision_packet_created": True,
            "future_executor_operator_"
            "decision_guard_report_created": True,
            "operator_decision_guard_passed": True,
            "future_operator_decision_"
            "required_before_any_order": True,
        }
    )

    return {
        "enablement_design_review": design,
        "enablement_guard_fixture": fixture,
        "enablement_review_packet": review,
        "operator_decision_packet": decision,
    }


def test_clean_chain_records_packet_review_only() -> None:
    report = build_stage_transition_review_report(
        legacy_outputs=_ready_outputs(),
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert (
        report["stage_transition_review_state"]
        == STATE_OPERATOR_DECISION_PACKET_REVIEW_ONLY
    )

    assert report["blocked"] is False

    assert (
        report["operator_decision_packet_ready"]
        is True
    )

    assert (
        report[
            "operator_decision_packet_is_operator_decision"
        ]
        is False
    )

    assert (
        report[
            "operator_decision_packet_is_runtime_authority"
        ]
        is False
    )

    assert (
        report[
            "operator_decision_packet_can_transition_stage"
        ]
        is False
    )

    assert (
        report["phase7_15_operator_decision_intake_required"]
        is True
    )

    assert (
        report["actual_operator_decision_recorded"]
        is False
    )

    assert (
        report["actual_stage_transition_performed"]
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


def test_fixture_failure_requires_evidence_repair() -> None:
    outputs = _ready_outputs()

    fixture = outputs[
        "enablement_guard_fixture"
    ]

    fixture[
        "phase7_12_guard_fixture_ready"
    ] = False

    fixture[
        "enablement_guard_fixture_guard_passed"
    ] = False

    fixture[
        "blocked"
    ] = True

    fixture[
        "fail_closed"
    ] = True

    report = build_stage_transition_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert (
        report["stage_transition_review_state"]
        == STATE_STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED
    )

    assert report["blocked"] is True

    assert (
        "FUTURE_EXECUTOR_ENABLEMENT_"
        "GUARD_FIXTURE_NOT_READY"
        in report["blockers"]
    )

    assert (
        report["testnet_order_submission_allowed"]
        is False
    )


def test_actual_operator_decision_is_exposed_and_blocked() -> None:
    outputs = _ready_outputs()

    outputs[
        "operator_decision_packet"
    ][
        "actual_operator_decision_recorded"
    ] = True

    report = build_stage_transition_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert (
        report["stage_transition_review_state"]
        == STATE_BLOCKED
    )

    assert report["blocked"] is True

    assert (
        report[
            "source_actual_operator_decision_recorded"
        ]
        is True
    )

    assert (
        report["actual_operator_decision_recorded"]
        is True
    )

    assert (
        "ACTUAL_OPERATOR_DECISION_RECORDED_UNEXPECTEDLY"
        in report["blockers"]
    )

    assert (
        report["operator_decision_runtime_authority"]
        is False
    )


def test_actual_stage_transition_is_exposed_and_blocked() -> None:
    outputs = _ready_outputs()

    outputs[
        "operator_decision_packet"
    ][
        "actual_stage_transition_performed"
    ] = True

    report = build_stage_transition_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert (
        report["stage_transition_review_state"]
        == STATE_BLOCKED
    )

    assert (
        report[
            "source_actual_stage_transition_performed"
        ]
        is True
    )

    assert (
        report["actual_stage_transition_performed"]
        is True
    )

    assert (
        report["stage_transition_authority"]
        is False
    )


def test_unsafe_order_permission_blocks_without_propagating() -> None:
    outputs = _ready_outputs()

    outputs[
        "enablement_review_packet"
    ][
        "testnet_order_submission_allowed"
    ] = True

    report = build_stage_transition_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert (
        report["stage_transition_review_state"]
        == STATE_BLOCKED
    )

    assert report["blocked"] is True

    assert (
        "STAGE_TRANSITION_COMPONENT_UNSAFE_FLAG:"
        "enablement_review_packet"
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
