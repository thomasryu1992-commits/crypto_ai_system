from __future__ import annotations

from crypto_ai_system.governance.readiness import (
    STATE_ACTUAL_INTAKE_REVIEW_ONLY,
    STATE_BLOCKED,
    STATE_WAITING_FOR_MANUAL_ARTIFACTS,
    build_readiness_review_report,
)


def _base_component(
    *,
    component_id_field: str,
    component_id: str,
    hash_field: str,
    hash_value: str,
    status: str,
    blocked: bool,
) -> dict:
    return {
        component_id_field: component_id,
        hash_field: hash_value,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "approval_intake_validated": False,
        "operator_unlock_request_validated": False,
        "signed_testnet_preparation_ready": False,
        "signed_testnet_readiness_passed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
    }


def _waiting_outputs() -> dict:
    preview = _base_component(
        component_id_field=(
            "phase6_signed_testnet_preparation_preview_id"
        ),
        component_id="preview_1",
        hash_field="phase6_report_sha256",
        hash_value="a" * 64,
        status=(
            "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_"
            "RECORDED_REVIEW_ONLY"
        ),
        blocked=False,
    )

    template = _base_component(
        component_id_field=(
            "phase6_1_signed_testnet_operator_unlock_"
            "request_template_id"
        ),
        component_id="template_1",
        hash_field="phase6_1_report_sha256",
        hash_value="b" * 64,
        status=(
            "PHASE6_1_SIGNED_TESTNET_OPERATOR_UNLOCK_"
            "REQUEST_TEMPLATE_RECORDED_REVIEW_ONLY"
        ),
        blocked=False,
    )
    template[
        "operator_unlock_request_template_created"
    ] = True

    fixtures = _base_component(
        component_id_field=(
            "phase6_2_operator_unlock_request_"
            "fixture_validator_id"
        ),
        component_id="fixtures_1",
        hash_field="phase6_2_report_sha256",
        hash_value="c" * 64,
        status=(
            "PHASE6_2_OPERATOR_UNLOCK_REQUEST_FIXTURE_"
            "VALIDATOR_RECORDED_REVIEW_ONLY"
        ),
        blocked=False,
    )
    fixtures[
        "valid_fixture_passed_review_only_validation"
    ] = True
    fixtures[
        "invalid_fixtures_blocked_fail_closed"
    ] = True

    gate = _base_component(
        component_id_field=(
            "phase6_3_signed_testnet_readiness_"
            "gate_review_id"
        ),
        component_id="gate_1",
        hash_field="phase6_3_report_sha256",
        hash_value="d" * 64,
        status=(
            "PHASE6_3_SIGNED_TESTNET_READINESS_GATE_"
            "BLOCKED_REVIEW_ONLY"
        ),
        blocked=True,
    )
    gate["missing_readiness_source_artifacts"] = []
    gate["unsafe_flags_by_artifact"] = {}

    packet = _base_component(
        component_id_field=(
            "phase6_4_signed_testnet_readiness_"
            "review_packet_id"
        ),
        component_id="packet_1",
        hash_field="phase6_4_review_packet_sha256",
        hash_value="e" * 64,
        status=(
            "PHASE6_4_SIGNED_TESTNET_READINESS_REVIEW_"
            "PACKET_RECORDED_REVIEW_ONLY"
        ),
        blocked=True,
    )
    packet["operator_decision_handoff_created"] = True
    packet[
        "missing_review_packet_source_artifacts"
    ] = []
    packet["unsafe_flags_by_artifact"] = {}

    sandbox = _base_component(
        component_id_field=(
            "phase6_5_actual_manual_approval_operator_"
            "unlock_intake_sandbox_id"
        ),
        component_id="sandbox_1",
        hash_field="phase6_5_report_sha256",
        hash_value="f" * 64,
        status=(
            "PHASE6_5_ACTUAL_APPROVAL_OPERATOR_UNLOCK_"
            "INTAKE_SANDBOX_BLOCKED_REVIEW_ONLY"
        ),
        blocked=True,
    )
    sandbox["actual_manual_approval_submission_present"] = False
    sandbox["actual_operator_unlock_request_present"] = False
    sandbox["missing_source_artifacts"] = []
    sandbox["unsafe_flags_by_artifact"] = {}

    bridge = _base_component(
        component_id_field=(
            "phase6_6_actual_intake_validation_bridge_id"
        ),
        component_id="bridge_1",
        hash_field="phase6_6_report_sha256",
        hash_value="1" * 64,
        status=(
            "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_"
            "BLOCKED_REVIEW_ONLY"
        ),
        blocked=True,
    )
    bridge["actual_manual_approval_submission_present"] = False
    bridge["actual_operator_unlock_request_present"] = False
    bridge["phase7_entry_review_possible"] = False
    bridge["missing_source_artifacts"] = []
    bridge["unsafe_flags_by_artifact"] = {}

    return {
        "preparation_preview": preview,
        "operator_unlock_template": template,
        "operator_unlock_fixtures": fixtures,
        "readiness_gate": gate,
        "readiness_packet": packet,
        "actual_intake_sandbox": sandbox,
        "actual_intake_bridge": bridge,
    }


def test_expected_manual_waiting_state_is_not_structural_failure() -> None:
    report = build_readiness_review_report(
        legacy_outputs=_waiting_outputs(),
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["readiness_state"]
        == STATE_WAITING_FOR_MANUAL_ARTIFACTS
    )
    assert report["blocked"] is False
    assert report["blockers"] == []
    assert (
        report["actual_manual_approval_submission_present"]
        is False
    )
    assert (
        report["actual_operator_unlock_request_present"]
        is False
    )
    assert report["runtime_permission_source"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_actual_intake_review_state_never_becomes_execution_authority() -> None:
    outputs = _waiting_outputs()

    outputs["actual_intake_sandbox"].update(
        {
            "status": (
                "PHASE6_5_ACTUAL_APPROVAL_OPERATOR_UNLOCK_"
                "INTAKE_SANDBOX_RECORDED_REVIEW_ONLY"
            ),
            "blocked": False,
            "fail_closed": False,
            "actual_manual_approval_submission_present": True,
            "actual_operator_unlock_request_present": True,
        }
    )

    outputs["actual_intake_bridge"].update(
        {
            "status": (
                "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_"
                "RECORDED_REVIEW_ONLY"
            ),
            "blocked": False,
            "fail_closed": False,
            "actual_manual_approval_submission_present": True,
            "actual_operator_unlock_request_present": True,
            "phase7_entry_review_possible": True,
        }
    )

    report = build_readiness_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert (
        report["readiness_state"]
        == STATE_ACTUAL_INTAKE_REVIEW_ONLY
    )
    assert report["blocked"] is False
    assert report["phase7_entry_review_possible"] is True
    assert report["phase7_execution_authority"] is False
    assert report["phase7_order_submission_authority"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False


def test_missing_upstream_readiness_evidence_blocks() -> None:
    outputs = _waiting_outputs()

    outputs["readiness_gate"][
        "missing_readiness_source_artifacts"
    ] = ["phase6_2_operator_unlock_request_fixture_validator"]

    report = build_readiness_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["readiness_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert (
        "READINESS_GATE_SOURCE_ARTIFACT_MISSING"
        in report["blockers"]
    )
    assert report["testnet_order_submission_allowed"] is False


def test_unsafe_component_flag_blocks_without_propagating_permission() -> None:
    outputs = _waiting_outputs()

    outputs["readiness_packet"][
        "testnet_order_submission_allowed"
    ] = True

    report = build_readiness_review_report(
        legacy_outputs=outputs,
        created_at_utc="2026-07-13T00:00:00Z",
    )

    assert report["readiness_state"] == STATE_BLOCKED
    assert report["blocked"] is True
    assert (
        "READINESS_COMPONENT_UNSAFE_FLAG:readiness_packet"
        in report["blockers"]
    )
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False
