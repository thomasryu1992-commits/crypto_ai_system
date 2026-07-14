from __future__ import annotations

from crypto_ai_system.governance.session_review import (
    STATE_BLOCKED,
    STATE_DISABLED_SESSION_REVIEW_ONLY,
    STATE_SESSION_EVIDENCE_REPAIR_REQUIRED,
    build_session_review_report,
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
        "signed_testnet_reconciliation_authority": False,
        "signed_testnet_session_close_authority": False,
        "signed_testnet_promotion_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "actual_reconciliation_authority": False,
        "actual_session_close_authority": False,
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
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
    }


def _ready_outputs() -> dict:
    reconciliation = _safe_base(
        id_field=(
            "phase7_4_disabled_execution_reconciliation_"
            "session_close_id"
        ),
        id_value="recon_1",
        hash_field="phase7_4_report_sha256",
        status=(
            "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_"
            "SESSION_CLOSE_RECORDED_REVIEW_ONLY"
        ),
    )
    reconciliation.update(
        {
            "phase7_4_reconciliation_session_close_ready": True,
            "disabled_execution_reconciled_review_only": True,
            "session_closed_review_only": True,
            "blocked_execution_evidence_linked": True,
            "reconciliation_mismatch": False,
            "observed_fill_count": 0,
            "observed_position_delta": 0.0,
            "observed_balance_delta": 0.0,
        }
    )

    review_packet = _safe_base(
        id_field=(
            "phase7_5_reconciliation_session_close_"
            "review_packet_id"
        ),
        id_value="packet_1",
        hash_field="phase7_5_report_sha256",
        status=(
            "PHASE7_5_RECONCILIATION_SESSION_CLOSE_"
            "REVIEW_PACKET_RECORDED_REVIEW_ONLY"
        ),
    )
    review_packet.update(
        {
            "phase7_5_review_packet_ready": True,
            "promotion_guard_passed": True,
            "disabled_execution_reconciled_review_only": True,
            "session_closed_review_only": True,
            "reconciliation_mismatch": False,
            "observed_fill_count": 0,
            "observed_position_delta": 0.0,
            "observed_balance_delta": 0.0,
        }
    )

    handoff = _safe_base(
        id_field=(
            "phase7_6_disabled_signed_testnet_session_"
            "operator_handoff_id"
        ),
        id_value="handoff_1",
        hash_field="phase7_6_report_sha256",
        status=(
            "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_"
            "OPERATOR_HANDOFF_RECORDED_REVIEW_ONLY"
        ),
    )
    handoff.update(
        {
            "phase7_6_operator_handoff_ready": True,
            "executor_approval_checklist_ready_review_only": True,
            "promotion_guard_passed": True,
            "disabled_execution_reconciled_review_only": True,
            "session_closed_review_only": True,
            "reconciliation_mismatch": False,
            "future_executor_approval_required_before_any_order": True,
            "observed_fill_count": 0,
            "observed_position_delta": 0.0,
            "observed_balance_delta": 0.0,
        }
    )

    return {
        "disabled_reconciliation_session_close": reconciliation,
        "reconciliation_session_close_review_packet": review_packet,
        "disabled_session_operator_handoff": handoff,
    }


def test_clean_disabled_session_records_review_only_state() -> None:
    report = build_session_review_report(
        legacy_outputs=_ready_outputs(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["session_review_state"]
        == STATE_DISABLED_SESSION_REVIEW_ONLY
    )
    assert report["blocked"] is False
    assert report["zero_effect_evidence"] is True
    assert report["observed_fill_count"] == 0
    assert report["observed_position_delta"] == 0.0
    assert report["observed_balance_delta"] == 0.0
    assert report["source_exchange_endpoint_call_detected"] is False
    assert report["future_executor_approval_required_before_any_order"] is True
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_reconciliation_mismatch_becomes_repair_required() -> None:
    outputs = _ready_outputs()

    outputs[
        "disabled_reconciliation_session_close"
    ]["reconciliation_mismatch"] = True

    outputs[
        "disabled_reconciliation_session_close"
    ]["phase7_4_reconciliation_session_close_ready"] = False

    outputs[
        "disabled_reconciliation_session_close"
    ]["blocked"] = True

    outputs[
        "disabled_reconciliation_session_close"
    ]["fail_closed"] = True

    report = build_session_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["session_review_state"]
        == STATE_SESSION_EVIDENCE_REPAIR_REQUIRED
    )
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["source_reconciliation_mismatch_detected"] is True
    assert report["testnet_order_submission_allowed"] is False


def test_nonzero_effect_evidence_requires_repair() -> None:
    outputs = _ready_outputs()

    outputs[
        "disabled_reconciliation_session_close"
    ]["observed_fill_count"] = 1

    report = build_session_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["session_review_state"]
        == STATE_SESSION_EVIDENCE_REPAIR_REQUIRED
    )
    assert report["zero_effect_evidence"] is False
    assert (
        "SESSION_REVIEW_NONZERO_OR_INVALID_EFFECT_EVIDENCE"
        in report["blockers"]
    )


def test_endpoint_call_evidence_is_exposed_and_blocks() -> None:
    outputs = _ready_outputs()

    outputs[
        "disabled_reconciliation_session_close"
    ]["exchange_endpoint_called"] = True

    report = build_session_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["session_review_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert report["source_exchange_endpoint_call_detected"] is True
    assert report["exchange_endpoint_called"] is True
    assert (
        "SESSION_REVIEW_SOURCE_ENDPOINT_CALL_DETECTED"
        in report["blockers"]
    )
    assert report["external_order_submission_allowed"] is False


def test_unsafe_source_permission_blocks_without_granting_permission() -> None:
    outputs = _ready_outputs()

    outputs[
        "disabled_session_operator_handoff"
    ]["testnet_order_submission_allowed"] = True

    report = build_session_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["session_review_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert (
        "SESSION_REVIEW_COMPONENT_UNSAFE_FLAG:"
        "disabled_session_operator_handoff"
        in report["blockers"]
    )
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
