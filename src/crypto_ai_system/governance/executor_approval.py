from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.utils.audit import (
    sha256_json,
    stable_id,
    utc_now_canonical,
)

from crypto_ai_system.governance.common import (
    bool_value as _bool,
    latest_dir as _latest_dir,
    storage_dir as _common_storage_dir,
    unsafe_true_fields as _common_unsafe_true_fields,
)

EXECUTOR_APPROVAL_VERSION = "lean_executor_approval_v1"

PHASE9_SINGLE_ORDER_REVIEW_VERSION = (
    "phase9_single_signed_testnet_order_approval_review_v1"
)

PHASE9_SINGLE_ORDER_REQUIRED_SCOPE_FIELDS: tuple[str, ...] = (
    "venue",
    "symbol",
    "side",
    "order_type",
    "max_notional_cap",
    "approval_expires_at_utc",
)


def _phase9_positive_number(
    value: Any,
) -> bool:
    if isinstance(value, bool):
        return False

    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _phase9_hash_without(
    payload: Mapping[str, Any],
    field: str,
) -> str:
    body = dict(payload)
    body.pop(field, None)
    return sha256_json(body)


def build_phase9_single_order_approval_review_packet(
    *,
    phase8_report: Mapping[str, Any] | None,
    proposed_order_scope: Mapping[str, Any] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a review-only Phase 9 packet on the existing approval framework.

    This packet never creates approval authority, enables an executor, signs a
    request, or grants order submission permission.
    """

    created = created_at_utc or utc_now_canonical()
    phase8 = dict(phase8_report or {})
    scope = dict(proposed_order_scope or {})
    blockers: list[str] = []

    phase8_hash = str(
        phase8.get("signed_testnet_execution_preparation_sha256")
        or ""
    )

    if not phase8:
        blockers.append("PHASE9_PHASE8_REPORT_MISSING")
    elif (
        not phase8_hash
        or phase8_hash
        != _phase9_hash_without(
            phase8,
            "signed_testnet_execution_preparation_sha256",
        )
    ):
        blockers.append("PHASE9_PHASE8_REPORT_HASH_INVALID")

    phase8_fresh_evidence_valid = (
        phase8.get("phase8_fresh_runtime_evidence_validated")
        is True
        and phase8.get(
            "phase8_integrated_runtime_validation_complete"
        )
        is True
        and phase8.get("phase8_completion_review_allowed")
        is True
        and phase8.get("phase9_approval_review_allowed")
        is True
        and phase8.get("phase8_execution_preparation_ready")
        is False
        and phase8.get("ready_for_signed_testnet_execution")
        is False
        and phase8.get("testnet_order_submission_allowed")
        is False
    )

    if not phase8_fresh_evidence_valid:
        blockers.append(
            "PHASE9_FRESH_PHASE8_RUNTIME_EVIDENCE_NOT_VALIDATED"
        )

    if not scope:
        blockers.append("PHASE9_SINGLE_ORDER_SCOPE_MISSING")

    if (
        str(scope.get("stage") or "").strip().lower()
        != "signed_testnet"
    ):
        blockers.append("PHASE9_SCOPE_STAGE_NOT_SIGNED_TESTNET")

    if scope.get("payload_frozen") is not True:
        blockers.append("PHASE9_SCOPE_ORDER_PAYLOAD_NOT_FROZEN")

    missing_scope_fields = sorted(
        field
        for field in PHASE9_SINGLE_ORDER_REQUIRED_SCOPE_FIELDS
        if not str(scope.get(field) or "").strip()
    )

    if missing_scope_fields:
        blockers.append(
            "PHASE9_SINGLE_ORDER_SCOPE_FIELD_MISSING:"
            + ",".join(missing_scope_fields)
        )

    if not _phase9_positive_number(
        scope.get("max_notional_cap")
    ):
        blockers.append("PHASE9_MAX_NOTIONAL_CAP_INVALID")

    maximum_order_count = scope.get(
        "maximum_order_count",
        1,
    )

    if maximum_order_count != 1:
        blockers.append(
            "PHASE9_MAXIMUM_ORDER_COUNT_MUST_EQUAL_ONE"
        )

    phase8_m3 = dict(
        phase8.get(
            "hot_path_pre_order_risk_gate_validation"
        )
        or {}
    )

    if (
        str(scope.get("order_intent_id") or "")
        != str(phase8_m3.get("final_order_intent_id") or "")
    ):
        blockers.append(
            "PHASE9_SCOPE_ORDER_INTENT_ID_MISMATCH"
        )

    if (
        str(scope.get("final_order_intent_sha256") or "")
        != str(phase8_m3.get("final_order_intent_sha256") or "")
    ):
        blockers.append(
            "PHASE9_SCOPE_ORDER_INTENT_HASH_MISMATCH"
        )

    if (
        str(scope.get("risk_gate_id") or "")
        != str(phase8_m3.get("risk_gate_id") or "")
    ):
        blockers.append("PHASE9_SCOPE_RISK_GATE_ID_MISMATCH")

    unsafe_scope_fields = _unsafe_true_fields(scope)

    if unsafe_scope_fields:
        blockers.append(
            "PHASE9_SCOPE_UNSAFE_PERMISSION_FIELD:"
            + ",".join(unsafe_scope_fields)
        )

    blockers = sorted(set(blockers))
    review_ready = not blockers

    if review_ready:
        status = (
            "PHASE9_SINGLE_ORDER_APPROVAL_REVIEW_"
            "PACKET_RECORDED_REVIEW_ONLY"
        )
        next_action = (
            "collect_explicit_operator_approval_for_exact_"
            "single_order_scope_keep_executor_disabled"
        )
    elif not phase8_fresh_evidence_valid:
        status = (
            "PHASE9_SINGLE_ORDER_APPROVAL_REVIEW_"
            "WAITING_FOR_FRESH_PHASE8_EVIDENCE"
        )
        next_action = (
            "collect_and_validate_fresh_phase8_runtime_"
            "evidence_keep_executor_disabled"
        )
    else:
        status = (
            "PHASE9_SINGLE_ORDER_APPROVAL_REVIEW_"
            "SCOPE_REPAIR_REQUIRED"
        )
        next_action = (
            "complete_exact_single_order_scope_and_"
            "rerun_review_keep_executor_disabled"
        )

    packet: dict[str, Any] = {
        "phase9_single_order_approval_review_packet_id": stable_id(
            "phase9_single_order_approval_review_packet",
            {
                "version": PHASE9_SINGLE_ORDER_REVIEW_VERSION,
                "phase8_report_sha256": phase8_hash,
                "order_intent_id": scope.get("order_intent_id"),
                "created_at_utc": created,
                "blockers": blockers,
            },
            24,
        ),
        "version": PHASE9_SINGLE_ORDER_REVIEW_VERSION,
        "status": status,
        "review_only": True,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "approval_scope": "single_signed_testnet_order",
        "single_order_only": True,
        "maximum_order_count": 1,
        "phase8_fresh_runtime_evidence_validated": (
            phase8_fresh_evidence_valid
        ),
        "source_phase8_report_id": phase8.get(
            "signed_testnet_execution_preparation_id"
        ),
        "source_phase8_report_sha256": phase8_hash or None,
        "source_phase8_runtime_evidence_validation_id": (
            phase8.get("phase8_runtime_evidence_validation_id")
        ),
        "proposed_order_scope": {
            "stage": scope.get("stage"),
            "order_intent_id": scope.get("order_intent_id"),
            "final_order_intent_sha256": scope.get(
                "final_order_intent_sha256"
            ),
            "risk_gate_id": scope.get("risk_gate_id"),
            "venue": scope.get("venue"),
            "symbol": scope.get("symbol"),
            "side": scope.get("side"),
            "order_type": scope.get("order_type"),
            "max_notional_cap": scope.get("max_notional_cap"),
            "approval_expires_at_utc": scope.get(
                "approval_expires_at_utc"
            ),
        },
        "required_operator_fields": list(
            PHASE9_SINGLE_ORDER_REQUIRED_SCOPE_FIELDS
        ),
        "phase9_single_order_approval_review_packet_ready": (
            review_ready
        ),
        "phase9_approval_review_allowed": review_ready,
        "explicit_operator_approval_required": True,
        "exact_order_scope_hash_required": True,
        "approval_expiry_required": True,
        "approval_reuse_allowed": False,
        "approval_scope_expansion_allowed": False,
        "actual_phase9_approval_created": False,
        "phase9_approval_runtime_authority": False,
        "phase9_executor_enablement_allowed": False,
        "phase9_request_signing_allowed": False,
        "phase9_order_submission_permission_granted": False,
        "phase9_order_submission_performed": False,
        "phase9_cancel_permission_granted": False,
        "phase9_cancel_performed": False,
        "blockers": blockers,
        "next_action": next_action,
        "runtime_permission_source": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
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
        "created_at_utc": created,
    }

    packet[
        "phase9_single_order_approval_review_packet_sha256"
    ] = sha256_json(packet)

    return packet


STATE_FIXTURE_REVIEW_ONLY = (
    "FUTURE_EXECUTOR_APPROVAL_FIXTURE_REVIEW_ONLY"
)

STATE_OPERATOR_SUBMISSION_REVIEW_ONLY = (
    "OPERATOR_SUBMISSION_VALIDATED_REVIEW_ONLY"
)

STATE_APPROVAL_EVIDENCE_REPAIR_REQUIRED = (
    "APPROVAL_EVIDENCE_REPAIR_REQUIRED"
)

STATE_BLOCKED = "BLOCKED"

STATUS_FIXTURE_RECORDED_REVIEW_ONLY = (
    "FUTURE_EXECUTOR_APPROVAL_FIXTURE_RECORDED_REVIEW_ONLY"
)

STATUS_OPERATOR_SUBMISSION_RECORDED_REVIEW_ONLY = (
    "OPERATOR_SUBMISSION_VALIDATED_RECORDED_REVIEW_ONLY"
)

STATUS_REPAIR_REQUIRED_REVIEW_ONLY = (
    "FUTURE_EXECUTOR_APPROVAL_EVIDENCE_REPAIR_REQUIRED_REVIEW_ONLY"
)

STATUS_BLOCKED_REVIEW_ONLY = (
    "FUTURE_EXECUTOR_APPROVAL_BLOCKED_REVIEW_ONLY"
)

_UNSAFE_FIELDS: tuple[str, ...] = (
    "runtime_permission_source",
    "executor_approval_runtime_authority",
    "executor_approval_authority",
    "executor_enablement_authority",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_executor_approval_authority",
    "signed_testnet_execution_authority",
    "signed_testnet_order_submission_authority",
    "signed_testnet_promotion_authority",
    "actual_executor_approval_created",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "actual_cancel_performed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "exchange_endpoint_called",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "auto_promotion_allowed",
)

_COMPONENT_SPECS: tuple[
    tuple[str, str, str],
    ...,
] = (
    (
        "future_executor_prerequisite_design",
        "phase7_7_future_executor_review_prerequisite_design_id",
        "phase7_7_report_sha256",
    ),
    (
        "future_executor_approval_template",
        "phase7_8_future_executor_approval_packet_template_id",
        "phase7_8_report_sha256",
    ),
    (
        "future_executor_approval_intake",
        "phase7_9_future_executor_approval_intake_validator_id",
        "phase7_9_report_sha256",
    ),
    (
        "future_executor_approval_review_packet",
        "phase7_10_future_executor_approval_review_packet_id",
        "phase7_10_report_sha256",
    ),
)




def _storage_dir(
    cfg: AppConfig,
) -> Path:
    return _common_storage_dir(
        cfg,
        "storage/governance/executor_approval",
    )





def _unsafe_true_fields(
    payload: Mapping[str, Any],
) -> list[str]:
    return _common_unsafe_true_fields(
        payload,
        fields=_UNSAFE_FIELDS,
    )



def _component_projection(
    *,
    name: str,
    payload: Mapping[str, Any] | None,
    id_field: str,
    hash_field: str,
) -> dict[str, Any]:
    source = dict(
        payload
        or {}
    )

    return {
        "component": name,
        "source_id": source.get(
            id_field
        ),
        "source_sha256": source.get(
            hash_field
        ),
        "status": source.get(
            "status"
        ),
        "blocked": (
            source.get("blocked")
            is True
        ),
        "fail_closed": (
            source.get("fail_closed")
            is True
        ),
        "review_only": (
            source.get("review_only")
            is True
        ),
        "unsafe_true_flags": (
            _unsafe_true_fields(
                source
            )
        ),
    }


def _structural_blockers(
    *,
    legacy_outputs: Mapping[
        str,
        Mapping[str, Any],
    ],
    components: Mapping[
        str,
        Mapping[str, Any],
    ],
) -> list[str]:
    blockers: list[str] = []

    for (
        name,
        _,
        _,
    ) in _COMPONENT_SPECS:
        source = dict(
            legacy_outputs.get(
                name
            )
            or {}
        )

        projection = dict(
            components.get(
                name
            )
            or {}
        )

        if not source:
            blockers.append(
                "EXECUTOR_APPROVAL_COMPONENT_MISSING:"
                + name
            )

            continue

        if not projection.get(
            "source_id"
        ):
            blockers.append(
                "EXECUTOR_APPROVAL_COMPONENT_ID_MISSING:"
                + name
            )

        if not projection.get(
            "status"
        ):
            blockers.append(
                "EXECUTOR_APPROVAL_COMPONENT_STATUS_MISSING:"
                + name
            )

        if projection.get(
            "unsafe_true_flags"
        ):
            blockers.append(
                "EXECUTOR_APPROVAL_COMPONENT_UNSAFE_FLAG:"
                + name
            )

    return blockers


def build_executor_approval_report(
    *,
    legacy_outputs: Mapping[
        str,
        Mapping[str, Any],
    ],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    components = {
        name: _component_projection(
            name=name,
            payload=legacy_outputs.get(
                name
            ),
            id_field=id_field,
            hash_field=hash_field,
        )
        for (
            name,
            id_field,
            hash_field,
        ) in _COMPONENT_SPECS
    }

    structural_blockers = (
        _structural_blockers(
            legacy_outputs=(
                legacy_outputs
            ),
            components=components,
        )
    )

    prerequisite = dict(
        legacy_outputs.get(
            "future_executor_prerequisite_design"
        )
        or {}
    )

    template = dict(
        legacy_outputs.get(
            "future_executor_approval_template"
        )
        or {}
    )

    intake = dict(
        legacy_outputs.get(
            "future_executor_approval_intake"
        )
        or {}
    )

    review = dict(
        legacy_outputs.get(
            "future_executor_approval_review_packet"
        )
        or {}
    )

    actual_operator_submission_present = (
        intake.get(
            "actual_operator_submission_present"
        )
        is True
    )

    validated_submission_source = (
        str(
            intake.get(
                "validated_submission_source"
            )
            or ""
        )
        .strip()
    )

    source_actual_executor_approval_created = any(
        source.get(
            "actual_executor_approval_created"
        )
        is True
        for source in (
            prerequisite,
            template,
            intake,
            review,
        )
    )

    source_actual_executor_enablement_performed = any(
        source.get(
            "actual_executor_enablement_performed"
        )
        is True
        for source in (
            prerequisite,
            template,
            intake,
            review,
        )
    )

    source_actual_order_submission_performed = any(
        source.get(
            "actual_order_submission_performed"
        )
        is True
        for source in (
            prerequisite,
            template,
            intake,
            review,
        )
    )

    source_actual_cancel_performed = any(
        source.get(
            "actual_cancel_performed"
        )
        is True
        for source in (
            prerequisite,
            template,
            intake,
            review,
        )
    )

    source_external_order_submission_performed = any(
        source.get(
            "external_order_submission_performed"
        )
        is True
        for source in (
            prerequisite,
            template,
            intake,
            review,
        )
    )

    source_exchange_endpoint_called = any(
        source.get(
            "exchange_endpoint_called"
        )
        is True
        for source in (
            prerequisite,
            template,
            intake,
            review,
        )
    )

    source_secret_value_accessed = any(
        source.get(
            "secret_value_accessed"
        )
        is True
        or source.get(
            "secret_file_read"
        )
        is True
        or source.get(
            "secret_file_created"
        )
        is True
        for source in (
            prerequisite,
            template,
            intake,
            review,
        )
    )

    prerequisite_ready = (
        prerequisite.get(
            "status"
        )
        == (
            "PHASE7_7_FUTURE_EXECUTOR_REVIEW_"
            "PREREQUISITE_DESIGN_RECORDED_REVIEW_ONLY"
        )
        and prerequisite.get(
            "phase7_7_prerequisite_design_ready"
        )
        is True
        and prerequisite.get(
            "future_executor_prerequisite_guard_passed"
        )
        is True
        and prerequisite.get(
            "future_executor_review_prerequisites_ready_review_only"
        )
        is True
        and prerequisite.get(
            "future_executor_review_required_before_any_order"
        )
        is True
        and prerequisite.get(
            "actual_executor_enablement_performed"
        )
        is False
        and prerequisite.get(
            "actual_order_submission_performed"
        )
        is False
        and prerequisite.get(
            "actual_cancel_performed"
        )
        is False
        and prerequisite.get(
            "external_order_submission_performed"
        )
        is False
        and prerequisite.get(
            "exchange_endpoint_called"
        )
        is False
        and prerequisite.get(
            "blocked"
        )
        is False
    )

    template_ready = (
        template.get(
            "status"
        )
        == (
            "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_"
            "TEMPLATE_RECORDED_REVIEW_ONLY"
        )
        and template.get(
            "phase7_8_template_ready"
        )
        is True
        and template.get(
            "future_executor_approval_template_created"
        )
        is True
        and template.get(
            "template_guard_passed"
        )
        is True
        and bool(
            template.get(
                "executor_approval_template_operator_required_fields"
            )
        )
        and template.get(
            "actual_executor_approval_created"
        )
        is False
        and template.get(
            "actual_executor_enablement_performed"
        )
        is False
        and template.get(
            "actual_order_submission_performed"
        )
        is False
        and template.get(
            "actual_cancel_performed"
        )
        is False
        and template.get(
            "external_order_submission_performed"
        )
        is False
        and template.get(
            "exchange_endpoint_called"
        )
        is False
        and template.get(
            "blocked"
        )
        is False
    )

    intake_ready = (
        intake.get(
            "status"
        )
        == (
            "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_"
            "VALIDATOR_RECORDED_REVIEW_ONLY"
        )
        and intake.get(
            "phase7_9_intake_validation_ready"
        )
        is True
        and intake.get(
            "intake_guard_passed"
        )
        is True
        and intake.get(
            "valid_future_executor_approval_submission_"
            "passed_review_only_validation"
        )
        is True
        and intake.get(
            "invalid_future_executor_approval_submission_"
            "fixtures_blocked_fail_closed"
        )
        is True
        and intake.get(
            "metadata_only_key_reference_validated_review_only"
        )
        is True
        and intake.get(
            "actual_executor_approval_created"
        )
        is False
        and intake.get(
            "actual_executor_enablement_performed"
        )
        is False
        and intake.get(
            "actual_order_submission_performed"
        )
        is False
        and intake.get(
            "actual_cancel_performed"
        )
        is False
        and intake.get(
            "external_order_submission_performed"
        )
        is False
        and intake.get(
            "exchange_endpoint_called"
        )
        is False
        and intake.get(
            "blocked"
        )
        is False
    )

    review_ready = (
        review.get(
            "status"
        )
        == (
            "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_"
            "REVIEW_PACKET_RECORDED_REVIEW_ONLY"
        )
        and review.get(
            "phase7_10_review_packet_ready"
        )
        is True
        and review.get(
            "review_guard_passed"
        )
        is True
        and review.get(
            "phase7_9_intake_validation_ready"
        )
        is True
        and review.get(
            "future_executor_approval_intake_"
            "validation_record_valid"
        )
        is True
        and review.get(
            "future_executor_approval_intake_"
            "guard_passed"
        )
        is True
        and review.get(
            "metadata_only_key_reference_"
            "validated_review_only"
        )
        is True
        and review.get(
            "prerequisite_packet_hash_matches"
        )
        is True
        and review.get(
            "hard_caps_numeric"
        )
        is True
        and review.get(
            "fresh_rechecks_true"
        )
        is True
        and review.get(
            "actual_executor_approval_created"
        )
        is False
        and review.get(
            "actual_executor_enablement_performed"
        )
        is False
        and review.get(
            "actual_order_submission_performed"
        )
        is False
        and review.get(
            "actual_cancel_performed"
        )
        is False
        and review.get(
            "external_order_submission_performed"
        )
        is False
        and review.get(
            "exchange_endpoint_called"
        )
        is False
        and review.get(
            "blocked"
        )
        is False
    )

    evidence_blockers: list[str] = []

    if not prerequisite_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_PREREQUISITE_DESIGN_NOT_READY"
        )

    if not template_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_APPROVAL_TEMPLATE_NOT_READY"
        )

    if not intake_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_APPROVAL_INTAKE_NOT_READY"
        )

    if not review_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_NOT_READY"
        )

    if (
        actual_operator_submission_present
        and validated_submission_source
        != "actual_operator_submission"
    ):
        evidence_blockers.append(
            "ACTUAL_OPERATOR_SUBMISSION_SOURCE_INCONSISTENT"
        )

    if (
        not actual_operator_submission_present
        and validated_submission_source
        != "valid_review_only_fixture"
    ):
        evidence_blockers.append(
            "FIXTURE_VALIDATION_SOURCE_INCONSISTENT"
        )

    safety_blockers: list[str] = []

    if (
        source_actual_executor_approval_created
    ):
        safety_blockers.append(
            "ACTUAL_EXECUTOR_APPROVAL_CREATED_UNEXPECTEDLY"
        )

    if (
        source_actual_executor_enablement_performed
    ):
        safety_blockers.append(
            "ACTUAL_EXECUTOR_ENABLEMENT_PERFORMED_UNEXPECTEDLY"
        )

    if (
        source_actual_order_submission_performed
    ):
        safety_blockers.append(
            "ACTUAL_ORDER_SUBMISSION_PERFORMED_UNEXPECTEDLY"
        )

    if (
        source_actual_cancel_performed
    ):
        safety_blockers.append(
            "ACTUAL_CANCEL_PERFORMED_UNEXPECTEDLY"
        )

    if (
        source_external_order_submission_performed
    ):
        safety_blockers.append(
            "EXTERNAL_ORDER_SUBMISSION_PERFORMED_UNEXPECTEDLY"
        )

    if (
        source_exchange_endpoint_called
    ):
        safety_blockers.append(
            "EXCHANGE_ENDPOINT_CALLED_UNEXPECTEDLY"
        )

    if (
        source_secret_value_accessed
    ):
        safety_blockers.append(
            "SECRET_VALUE_OR_FILE_ACCESS_DETECTED"
        )

    blockers = sorted(
        set(
            structural_blockers
            + evidence_blockers
            + safety_blockers
        )
    )

    if not blockers:
        if (
            actual_operator_submission_present
        ):
            state = (
                STATE_OPERATOR_SUBMISSION_REVIEW_ONLY
            )

            status = (
                STATUS_OPERATOR_SUBMISSION_RECORDED_REVIEW_ONLY
            )

            next_action = (
                "prepare_phase7_future_executor_"
                "enablement_design_review_only_"
                "without_runtime_authority"
            )
        else:
            state = (
                STATE_FIXTURE_REVIEW_ONLY
            )

            status = (
                STATUS_FIXTURE_RECORDED_REVIEW_ONLY
            )

            next_action = (
                "continue_enablement_design_review_only_"
                "while_fixture_remains_non_authoritative"
            )

    elif (
        structural_blockers
        or safety_blockers
    ):
        state = STATE_BLOCKED

        status = (
            STATUS_BLOCKED_REVIEW_ONLY
        )

        next_action = (
            "resolve_executor_approval_"
            "structural_or_safety_blockers"
        )

    else:
        state = (
            STATE_APPROVAL_EVIDENCE_REPAIR_REQUIRED
        )

        status = (
            STATUS_REPAIR_REQUIRED_REVIEW_ONLY
        )

        next_action = (
            "repair_executor_approval_"
            "evidence_and_rerun_review"
        )

    seed = {
        "version": (
            EXECUTOR_APPROVAL_VERSION
        ),
        "state": state,
        "component_ids": {
            name: projection.get(
                "source_id"
            )
            for (
                name,
                projection,
            ) in components.items()
        },
        "actual_operator_submission_present": (
            actual_operator_submission_present
        ),
        "created_at_utc": created,
    }

    report: dict[str, Any] = {
        "executor_approval_review_id": (
            stable_id(
                "executor_approval_review",
                seed,
                24,
            )
        ),
        "executor_approval_review_version": (
            EXECUTOR_APPROVAL_VERSION
        ),
        "status": status,
        "executor_approval_review_state": (
            state
        ),
        "blocked": bool(
            blockers
        ),
        "fail_closed": bool(
            blockers
        ),
        "review_only": True,
        "future_executor_approval_review_only": True,
        "actual_operator_submission_present": (
            actual_operator_submission_present
        ),
        "validated_submission_source": (
            validated_submission_source
        ),
        "fixture_validation_only": (
            not actual_operator_submission_present
        ),
        "fixture_validation_is_executor_approval": False,
        "operator_submission_validation_is_runtime_authority": False,
        "actual_executor_approval_created": (
            source_actual_executor_approval_created
        ),
        "executor_approval_runtime_authority": False,
        "future_executor_prerequisite_design_ready": (
            prerequisite_ready
        ),
        "future_executor_approval_template_ready": (
            template_ready
        ),
        "future_executor_approval_intake_ready": (
            intake_ready
        ),
        "future_executor_approval_review_packet_ready": (
            review_ready
        ),
        "metadata_only_key_reference_validated_review_only": (
            intake.get(
                "metadata_only_key_reference_"
                "validated_review_only"
            )
            is True
            and review.get(
                "metadata_only_key_reference_"
                "validated_review_only"
            )
            is True
        ),
        "prerequisite_packet_hash_matches": (
            review.get(
                "prerequisite_packet_hash_matches"
            )
            is True
        ),
        "hard_caps_numeric": (
            review.get(
                "hard_caps_numeric"
            )
            is True
        ),
        "fresh_rechecks_true": (
            review.get(
                "fresh_rechecks_true"
            )
            is True
        ),
        "future_executor_approval_review_required_before_enablement": True,
        "future_executor_enablement_review_required_before_any_order": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "components": components,
        "blockers": blockers,
        "next_action": (
            next_action
        ),
        "source_actual_executor_approval_created": (
            source_actual_executor_approval_created
        ),
        "source_actual_executor_enablement_performed": (
            source_actual_executor_enablement_performed
        ),
        "source_actual_order_submission_performed": (
            source_actual_order_submission_performed
        ),
        "source_actual_cancel_performed": (
            source_actual_cancel_performed
        ),
        "source_external_order_submission_performed": (
            source_external_order_submission_performed
        ),
        "source_exchange_endpoint_called": (
            source_exchange_endpoint_called
        ),
        "source_secret_value_or_file_access_detected": (
            source_secret_value_accessed
        ),
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "actual_executor_enablement_performed": (
            source_actual_executor_enablement_performed
        ),
        "actual_order_submission_performed": (
            source_actual_order_submission_performed
        ),
        "actual_cancel_performed": (
            source_actual_cancel_performed
        ),
        "external_order_submission_performed": (
            source_external_order_submission_performed
        ),
        "exchange_endpoint_called": (
            source_exchange_endpoint_called
        ),
        "secret_value_accessed": (
            source_secret_value_accessed
        ),
        "secret_file_read": (
            source_secret_value_accessed
        ),
        "secret_file_created": (
            source_secret_value_accessed
        ),
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
        "created_at_utc": (
            created
        ),
    }

    report[
        "executor_approval_review_sha256"
    ] = sha256_json(
        report
    )

    return report


def run_executor_approval_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    run_session_review_first: bool = True,
    session_review_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    prerequisite_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    template_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    intake_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    review_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
) -> dict[str, Any]:
    """Run Phase 7.7-7.10 behind one review-only semantic entry point."""

    cfg = (
        cfg
        or load_config(
            project_root
        )
    )

    if (
        run_session_review_first
    ):
        if (
            session_review_runner
            is None
        ):
            from crypto_ai_system.governance.session_review import (
                run_session_review_chain,
            )

            session_review_runner = (
                run_session_review_chain
            )

        session_review_runner(
            cfg=cfg
        )

    if (
        prerequisite_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.executor_prerequisite import (
            persist_phase7_7_future_executor_review_prerequisite_design_report,
        )

        prerequisite_runner = (
            persist_phase7_7_future_executor_review_prerequisite_design_report
        )

    if (
        template_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.executor_approval_template import (
            persist_phase7_8_future_executor_approval_packet_template_report,
        )

        template_runner = (
            persist_phase7_8_future_executor_approval_packet_template_report
        )

    if (
        intake_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.executor_approval_intake import (
            persist_phase7_9_future_executor_approval_intake_validator_report,
        )

        intake_runner = (
            persist_phase7_9_future_executor_approval_intake_validator_report
        )

    if (
        review_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.executor_approval_packet_review import (
            persist_phase7_10_future_executor_approval_review_packet_report,
        )

        review_runner = (
            persist_phase7_10_future_executor_approval_review_packet_report
        )

    prerequisite = dict(
        prerequisite_runner(
            cfg=cfg,
            run_phase7_6_first=False,
        )
    )

    template = dict(
        template_runner(
            cfg=cfg,
            run_phase7_7_first=False,
        )
    )

    intake = dict(
        intake_runner(
            cfg=cfg,
            run_phase7_8_first=False,
        )
    )

    review = dict(
        review_runner(
            cfg=cfg,
            run_phase7_9_first=False,
        )
    )

    legacy_outputs = {
        "future_executor_prerequisite_design": (
            prerequisite
        ),
        "future_executor_approval_template": (
            template
        ),
        "future_executor_approval_intake": (
            intake
        ),
        "future_executor_approval_review_packet": (
            review
        ),
    }

    report = (
        build_executor_approval_report(
            legacy_outputs=(
                legacy_outputs
            ),
        )
    )

    latest = _latest_dir(
        cfg
    )

    storage = _storage_dir(
        cfg
    )

    atomic_write_json(
        latest
        / "executor_approval_review_report.json",
        report,
    )

    atomic_write_json(
        storage
        / "executor_approval_review_report.json",
        report,
    )

    return {
        "report": report,
        "legacy_outputs": (
            legacy_outputs
        ),
    }


def run_executor_approval_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return (
        run_executor_approval_chain(
            cfg=cfg,
            project_root=(
                project_root
            ),
        )["report"]
    )


__all__ = [
    "EXECUTOR_APPROVAL_VERSION",
    "STATE_FIXTURE_REVIEW_ONLY",
    "STATE_OPERATOR_SUBMISSION_REVIEW_ONLY",
    "STATE_APPROVAL_EVIDENCE_REPAIR_REQUIRED",
    "STATE_BLOCKED",
    "STATUS_FIXTURE_RECORDED_REVIEW_ONLY",
    "STATUS_OPERATOR_SUBMISSION_RECORDED_REVIEW_ONLY",
    "STATUS_REPAIR_REQUIRED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "PHASE9_SINGLE_ORDER_REVIEW_VERSION",
    "PHASE9_SINGLE_ORDER_REQUIRED_SCOPE_FIELDS",
    "build_phase9_single_order_approval_review_packet",
    "build_executor_approval_report",
    "run_executor_approval_chain",
    "run_executor_approval_latest",
]
