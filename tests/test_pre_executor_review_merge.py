from __future__ import annotations

from crypto_ai_system.governance.pre_executor_review import (
    APPROVE_OPTION,
    DEFER_OPTION,
    REJECT_OPTION,
    STATE_BLOCKED,
    STATE_OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY,
    STATE_OPERATOR_DECISION_DEFERRED_REVIEW_ONLY,
    STATE_OPERATOR_DECISION_REJECTED_REVIEW_ONLY,
    STATE_WAITING_FOR_OPERATOR_DECISION,
    build_final_pre_executor_review_packet,
    build_operator_decision_intake_template,
    build_pre_executor_review_report,
    validate_operator_decision_intake,
)


def _sources() -> dict:
    stage_transition = {
        "stage_transition_review_id": "stage_transition_1",
        "stage_transition_review_sha256": "a" * 64,
        "stage_transition_review_state": (
            "OPERATOR_DECISION_PACKET_REVIEW_ONLY"
        ),
        "operator_decision_packet_ready": True,
        "operator_decision_packet_is_runtime_authority": False,
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "testnet_order_submission_allowed": False,
        "signed_order_executor_enabled": False,
    }

    phase7_14 = {
        "phase7_14_future_executor_operator_decision_packet_id": (
            "phase7_14_1"
        ),
        "phase7_14_report_sha256": "b" * 64,
        "status": (
            "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_"
            "DECISION_PACKET_RECORDED_REVIEW_ONLY"
        ),
        "phase7_14_operator_decision_packet_ready": True,
        "operator_decision_guard_passed": True,
        "actual_operator_decision_recorded": False,
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "testnet_order_submission_allowed": False,
        "signed_order_executor_enabled": False,
    }

    packet = {
        "packet_type": (
            "future_signed_testnet_executor_"
            "operator_decision_packet_review_only"
        ),
        "future_executor_operator_decision_packet_sha256": (
            "c" * 64
        ),
        "review_only": True,
        "operator_decision_packet_only": True,
        "not_runtime_authority": True,
        "testnet_order_submission_allowed": False,
        "signed_order_executor_enabled": False,
    }

    guard = {
        "guard_type": (
            "future_signed_testnet_executor_"
            "operator_decision_guard_review_only"
        ),
        "future_executor_operator_decision_guard_report_sha256": (
            "d" * 64
        ),
        "guard_passed": True,
        "review_only": True,
        "actual_operator_decision_recorded": False,
        "testnet_order_submission_allowed": False,
        "signed_order_executor_enabled": False,
    }

    return {
        "stage_transition_review": stage_transition,
        "phase7_14_report": phase7_14,
        "operator_decision_packet": packet,
        "operator_decision_guard": guard,
    }


def _template() -> dict:
    sources = _sources()

    return build_operator_decision_intake_template(
        **sources,
        created_at_utc="2026-07-14T00:00:00Z",
    )


def _valid_submission(
    *,
    decision_option: str = APPROVE_OPTION,
) -> dict:
    template = _template()

    return {
        "operator_decision_id": "operator_decision_001",
        "operator_decision_intake_id": "operator_intake_001",
        "operator_id": "operator_thomas",
        "operator_ticket_or_signature": "ticket_reference_001",
        "canonical_utc_timestamp": "2026-07-14T01:00:00Z",
        "decision_option": decision_option,
        "decision_reason": "Manual review completed for preparation only.",
        "source_stage_transition_review_id": (
            template["source_stage_transition_review_id"]
        ),
        "source_stage_transition_review_hash": (
            template["source_stage_transition_review_hash"]
        ),
        "source_phase7_14_report_id": (
            template["source_phase7_14_report_id"]
        ),
        "source_phase7_14_report_hash": (
            template["source_phase7_14_report_hash"]
        ),
        "source_operator_decision_packet_hash": (
            template["source_operator_decision_packet_hash"]
        ),
        "source_operator_decision_guard_hash": (
            template["source_operator_decision_guard_hash"]
        ),
        "metadata_only_key_reference_id": "key_reference_testnet_001",
        "metadata_only_key_fingerprint": "0123456789abcdef" * 4,
        "max_testnet_notional_usd": 25.0,
        "max_testnet_order_count": 1,
        "max_testnet_daily_loss_usd": 10.0,
        "manual_kill_switch_confirmation": True,
        "hard_caps_rechecked": True,
        "pre_order_risk_gate_rechecked": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "runtime_permission_source": False,
        "operator_decision_runtime_authority": False,
        "stage_transition_authority": False,
        "actual_stage_transition_performed": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "auto_promotion_allowed": False,
    }


def _validate(
    submission: dict | None,
) -> dict:
    template = _template()

    expected = {
        field: template[field]
        for field in (
            "source_stage_transition_review_id",
            "source_stage_transition_review_hash",
            "source_phase7_14_report_id",
            "source_phase7_14_report_hash",
            "source_operator_decision_packet_hash",
            "source_operator_decision_guard_hash",
        )
    }

    return validate_operator_decision_intake(
        submission=submission,
        expected_source=expected,
        created_at_utc="2026-07-14T02:00:00Z",
    )


def test_template_never_writes_or_grants_authority() -> None:
    template = _template()

    assert template["review_only"] is True
    assert template["template_only"] is True
    assert template["do_not_write_automatically"] is True

    assert (
        template["operator_decision_packet_is_operator_decision"]
        is False
    )

    assert (
        template["operator_decision_intake_is_runtime_authority"]
        is False
    )

    assert (
        template["operator_decision_intake_can_transition_stage"]
        is False
    )

    assert (
        template["testnet_order_submission_allowed"]
        is False
    )

    assert (
        template["signed_order_executor_enabled"]
        is False
    )


def test_missing_submission_waits_without_fixture_fallback() -> None:
    validation = _validate(
        None
    )

    assert (
        validation["waiting_for_operator_decision"]
        is True
    )

    assert (
        validation["actual_operator_submission_present"]
        is False
    )

    assert (
        validation["operator_decision_intake_validated"]
        is False
    )

    assert (
        validation["actual_operator_decision_recorded"]
        is False
    )

    assert validation["blocked"] is False

    assert (
        validation["blockers"]
        == [
            "OPERATOR_DECISION_SUBMISSION_MISSING"
        ]
    )

    packet = build_final_pre_executor_review_packet(
        intake_template=_template(),
        intake_validation=validation,
        created_at_utc="2026-07-14T03:00:00Z",
    )

    assert (
        packet["pre_executor_review_state"]
        == STATE_WAITING_FOR_OPERATOR_DECISION
    )

    assert (
        packet["final_pre_executor_review_ready"]
        is False
    )

    assert (
        packet["phase8_preparation_design_review_allowed"]
        is False
    )


def test_valid_approve_allows_only_phase8_preparation_review() -> None:
    validation = _validate(
        _valid_submission()
    )

    assert (
        validation["operator_decision_intake_validated"]
        is True
    )

    assert (
        validation["actual_operator_decision_recorded"]
        is True
    )

    assert (
        validation["phase8_preparation_review_allowed"]
        is True
    )

    assert (
        validation["operator_decision_runtime_authority"]
        is False
    )

    packet = build_final_pre_executor_review_packet(
        intake_template=_template(),
        intake_validation=validation,
        created_at_utc="2026-07-14T03:00:00Z",
    )

    assert (
        packet["pre_executor_review_state"]
        == (
            STATE_OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY
        )
    )

    assert (
        packet["final_pre_executor_review_ready"]
        is True
    )

    assert (
        packet["phase8_preparation_design_review_allowed"]
        is True
    )

    assert (
        packet["phase8_execution_allowed"]
        is False
    )

    assert (
        packet["phase8_write_path_allowed"]
        is False
    )

    assert (
        packet["phase8_executor_enablement_allowed"]
        is False
    )

    assert (
        packet["phase8_order_submission_allowed"]
        is False
    )

    assert (
        packet["ready_for_signed_testnet_execution"]
        is False
    )

    assert (
        packet["testnet_order_submission_allowed"]
        is False
    )


def test_defer_and_reject_do_not_open_phase8() -> None:
    deferred = _validate(
        _valid_submission(
            decision_option=DEFER_OPTION,
        )
    )

    deferred_packet = (
        build_final_pre_executor_review_packet(
            intake_template=_template(),
            intake_validation=deferred,
            created_at_utc="2026-07-14T03:00:00Z",
        )
    )

    assert (
        deferred_packet["pre_executor_review_state"]
        == STATE_OPERATOR_DECISION_DEFERRED_REVIEW_ONLY
    )

    assert (
        deferred_packet["phase8_preparation_design_review_allowed"]
        is False
    )

    rejected = _validate(
        _valid_submission(
            decision_option=REJECT_OPTION,
        )
    )

    rejected_packet = (
        build_final_pre_executor_review_packet(
            intake_template=_template(),
            intake_validation=rejected,
            created_at_utc="2026-07-14T03:00:00Z",
        )
    )

    assert (
        rejected_packet["pre_executor_review_state"]
        == STATE_OPERATOR_DECISION_REJECTED_REVIEW_ONLY
    )

    assert (
        rejected_packet["phase8_preparation_design_review_allowed"]
        is False
    )


def test_hash_mismatch_cap_excess_and_unsafe_flag_block() -> None:
    submission = _valid_submission()

    submission["source_phase7_14_report_hash"] = (
        "f" * 64
    )

    submission["max_testnet_notional_usd"] = 26.0

    submission["testnet_order_submission_allowed"] = True

    validation = _validate(
        submission
    )

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True

    assert (
        validation["operator_decision_intake_validated"]
        is False
    )

    assert (
        "OPERATOR_DECISION_SOURCE_MISMATCH:"
        "source_phase7_14_report_hash"
        in validation["blockers"]
    )

    assert (
        "MAX_TESTNET_NOTIONAL_INVALID_OR_EXCEEDS_REVIEW_CAP"
        in validation["blockers"]
    )

    assert any(
        blocker.startswith(
            "UNSAFE_OPERATOR_DECISION_FLAGS:"
        )
        for blocker in validation["blockers"]
    )

    packet = build_final_pre_executor_review_packet(
        intake_template=_template(),
        intake_validation=validation,
        created_at_utc="2026-07-14T03:00:00Z",
    )

    assert (
        packet["pre_executor_review_state"]
        == STATE_BLOCKED
    )

    assert (
        packet["testnet_order_submission_allowed"]
        is False
    )


def test_secret_value_field_is_rejected() -> None:
    submission = _valid_submission()

    submission["api_secret_value"] = "forbidden"

    validation = _validate(
        submission
    )

    assert validation["blocked"] is True

    assert any(
        blocker.startswith(
            "FORBIDDEN_SECRET_VALUE_FIELDS_PRESENT:"
        )
        for blocker in validation["blockers"]
    )


def test_aggregate_report_keeps_review_only_boundary() -> None:
    sources = _sources()

    template = _template()

    validation = _validate(
        _valid_submission()
    )

    final_packet = (
        build_final_pre_executor_review_packet(
            intake_template=template,
            intake_validation=validation,
            created_at_utc="2026-07-14T03:00:00Z",
        )
    )

    report = build_pre_executor_review_report(
        **sources,
        intake_template=template,
        intake_validation=validation,
        final_packet=final_packet,
        created_at_utc="2026-07-14T04:00:00Z",
    )

    assert (
        report["pre_executor_review_state"]
        == (
            STATE_OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY
        )
    )

    assert report["blocked"] is False

    assert (
        report["actual_operator_decision_recorded"]
        is True
    )

    assert (
        report["operator_decision_is_runtime_authority"]
        is False
    )

    assert (
        report["operator_decision_can_transition_stage"]
        is False
    )

    assert (
        report["phase8_preparation_design_review_allowed"]
        is True
    )

    assert (
        report["phase8_execution_allowed"]
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
