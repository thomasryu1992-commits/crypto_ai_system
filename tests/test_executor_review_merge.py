from __future__ import annotations

from crypto_ai_system.governance.executor_review import (
    STATE_BLOCKED,
    STATE_DISABLED_EXECUTOR_REVIEW_ONLY,
    STATE_REVIEW_CHAIN_REPAIR_REQUIRED,
    build_executor_review_report,
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
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_enablement_authority": False,
        "signed_testnet_order_submission_authority": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
    }


def _ready_outputs() -> dict:
    design = _safe_base(
        id_field=(
            "phase7_signed_testnet_validation_"
            "design_guard_id"
        ),
        id_value="design_1",
        hash_field="phase7_report_sha256",
        status=(
            "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_"
            "RECORDED_REVIEW_ONLY"
        ),
    )
    design["phase7_design_ready_review_only"] = True

    payload = _safe_base(
        id_field=(
            "phase7_1_signed_testnet_pre_submit_"
            "payload_guard_id"
        ),
        id_value="payload_1",
        hash_field="phase7_1_report_sha256",
        status=(
            "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_"
            "PAYLOAD_GUARD_RECORDED_REVIEW_ONLY"
        ),
    )
    payload["phase7_1_payload_guard_ready_review_only"] = True
    payload[
        "valid_would_submit_payload_"
        "passed_review_only_validation"
    ] = True
    payload[
        "invalid_payload_fixtures_"
        "blocked_fail_closed"
    ] = True
    payload["disabled_executor_guard_passed"] = True

    doctor = _safe_base(
        id_field=(
            "phase7_1_1_review_chain_state_doctor_id"
        ),
        id_value="doctor_1",
        hash_field="phase7_1_1_report_sha256",
        status=(
            "PHASE7_1_1_REVIEW_CHAIN_STATE_DOCTOR_"
            "RECORDED_REVIEW_ONLY"
        ),
    )
    doctor["phase7_1_chain_ready_review_only"] = True
    doctor["doctor_summary"] = {
        "review_only_actual_fixtures_synced": True,
    }

    enablement = _safe_base(
        id_field=(
            "phase7_2_executor_enablement_"
            "review_packet_id"
        ),
        id_value="enablement_1",
        hash_field="phase7_2_report_sha256",
        status=(
            "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_"
            "PACKET_RECORDED_REVIEW_ONLY"
        ),
    )
    enablement[
        "phase7_2_executor_enablement_review_ready"
    ] = True

    disabled = _safe_base(
        id_field=(
            "phase7_3_disabled_signed_testnet_"
            "executor_review_id"
        ),
        id_value="disabled_1",
        hash_field="phase7_3_report_sha256",
        status=(
            "PHASE7_3_DISABLED_SIGNED_TESTNET_"
            "EXECUTOR_REVIEW_RECORDED_REVIEW_ONLY"
        ),
    )
    disabled[
        "phase7_3_disabled_executor_review_ready"
    ] = True
    disabled["submit_order_blocked_review_only"] = True
    disabled["cancel_order_blocked_review_only"] = True
    disabled[
        "invalid_payload_fixtures_blocked_fail_closed"
    ] = True
    disabled["exchange_endpoint_called"] = False
    disabled["endpoint_call_count"] = 0

    return {
        "validation_design": design,
        "pre_submit_payload_guard": payload,
        "review_chain_doctor": doctor,
        "enablement_review_packet": enablement,
        "disabled_executor_review": disabled,
    }


def test_ready_chain_records_disabled_executor_review_only() -> None:
    report = build_executor_review_report(
        legacy_outputs=_ready_outputs(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["executor_review_state"]
        == STATE_DISABLED_EXECUTOR_REVIEW_ONLY
    )
    assert report["blocked"] is False
    assert report["disabled_executor_evidence_ready"] is True
    assert report["submit_order_blocked_review_only"] is True
    assert report["cancel_order_blocked_review_only"] is True
    assert report["exchange_endpoint_called"] is False
    assert report["endpoint_call_count"] == 0
    assert (
        report["review_only_fixture_sync_is_runtime_approval"]
        is False
    )
    assert report["runtime_approval_created_by_doctor"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_doctor_failure_becomes_repair_required() -> None:
    outputs = _ready_outputs()
    doctor = outputs["review_chain_doctor"]
    doctor["status"] = (
        "PHASE7_1_1_REVIEW_CHAIN_STATE_DOCTOR_"
        "BLOCKED_REVIEW_ONLY"
    )
    doctor["blocked"] = True
    doctor["fail_closed"] = True
    doctor["phase7_1_chain_ready_review_only"] = False

    report = build_executor_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["executor_review_state"]
        == STATE_REVIEW_CHAIN_REPAIR_REQUIRED
    )
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["testnet_order_submission_allowed"] is False


def test_endpoint_call_evidence_blocks_fail_closed() -> None:
    outputs = _ready_outputs()
    disabled = outputs["disabled_executor_review"]
    disabled["exchange_endpoint_called"] = True
    disabled["endpoint_call_count"] = 1

    report = build_executor_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["executor_review_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert (
        "DISABLED_EXECUTOR_ENDPOINT_CALL_EVIDENCE_INVALID"
        in report["blockers"]
    )
    assert report["exchange_endpoint_called"] is True
    assert report["endpoint_call_count"] == 1
    assert report["external_order_submission_allowed"] is False


def test_unsafe_source_flag_blocks_without_propagating_permission() -> None:
    outputs = _ready_outputs()
    outputs["enablement_review_packet"][
        "testnet_order_submission_allowed"
    ] = True

    report = build_executor_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["executor_review_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert (
        "EXECUTOR_REVIEW_COMPONENT_UNSAFE_FLAG:"
        "enablement_review_packet"
        in report["blockers"]
    )
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
