from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.utils.audit import (
    sha256_json,
    stable_id,
    utc_now_canonical,
)

from crypto_ai_system.governance.common import (
    artifact_hash as _artifact_hash,
    bool_value as _bool,
    canonical_utc_value as _canonical_utc_valid,
    forbidden_secret_fields as _forbidden_secret_fields,
    hex_fingerprint_valid as _hex_fingerprint_valid,
    latest_dir as _latest_dir,
    placeholder_value as _is_placeholder,
    positive_integer_within as _positive_integer_within,
    positive_number_within as _positive_within,
    safe_text as _safe_text,
    storage_dir as _common_storage_dir,
    unsafe_true_fields as _common_unsafe_true_fields,
)

PRE_EXECUTOR_REVIEW_VERSION = (
    "lean_pre_executor_review_v1"
)

STATE_WAITING_FOR_OPERATOR_DECISION = (
    "WAITING_FOR_OPERATOR_DECISION"
)

STATE_OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY = (
    "OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY"
)

STATE_OPERATOR_DECISION_DEFERRED_REVIEW_ONLY = (
    "OPERATOR_DECISION_DEFERRED_REVIEW_ONLY"
)

STATE_OPERATOR_DECISION_REJECTED_REVIEW_ONLY = (
    "OPERATOR_DECISION_REJECTED_REVIEW_ONLY"
)

STATE_BLOCKED = "BLOCKED"

STATUS_WAITING_REVIEW_ONLY = (
    "PRE_EXECUTOR_REVIEW_WAITING_FOR_OPERATOR_DECISION_"
    "REVIEW_ONLY"
)

STATUS_APPROVED_REVIEW_ONLY = (
    "PRE_EXECUTOR_REVIEW_PHASE8_PREPARATION_APPROVED_"
    "REVIEW_ONLY"
)

STATUS_DEFERRED_REVIEW_ONLY = (
    "PRE_EXECUTOR_REVIEW_OPERATOR_DECISION_DEFERRED_"
    "REVIEW_ONLY"
)

STATUS_REJECTED_REVIEW_ONLY = (
    "PRE_EXECUTOR_REVIEW_OPERATOR_DECISION_REJECTED_"
    "REVIEW_ONLY"
)

STATUS_BLOCKED_REVIEW_ONLY = (
    "PRE_EXECUTOR_REVIEW_BLOCKED_REVIEW_ONLY"
)

APPROVE_OPTION = (
    "APPROVE_FUTURE_EXECUTOR_REVIEW_ONLY_NOT_ENABLEMENT"
)

DEFER_OPTION = (
    "DEFER_FUTURE_EXECUTOR_REVIEW"
)

REJECT_OPTION = (
    "REJECT_FUTURE_EXECUTOR_REVIEW"
)

ALLOWED_DECISION_OPTIONS: tuple[str, ...] = (
    APPROVE_OPTION,
    DEFER_OPTION,
    REJECT_OPTION,
)

SUBMISSION_RELATIVE_PATH = (
    "storage/manual_operator_decision/"
    "operator_decision_intake_submission.json"
)

MAX_TESTNET_NOTIONAL_USD = 25.0
MAX_TESTNET_ORDER_COUNT = 1
MAX_TESTNET_DAILY_LOSS_USD = 10.0

REQUIRED_SUBMISSION_FIELDS: tuple[str, ...] = (
    "operator_decision_id",
    "operator_decision_intake_id",
    "operator_id",
    "operator_ticket_or_signature",
    "canonical_utc_timestamp",
    "decision_option",
    "decision_reason",
    "source_stage_transition_review_id",
    "source_stage_transition_review_hash",
    "source_phase7_14_report_id",
    "source_phase7_14_report_hash",
    "source_operator_decision_packet_hash",
    "source_operator_decision_guard_hash",
    "metadata_only_key_reference_id",
    "metadata_only_key_fingerprint",
    "max_testnet_notional_usd",
    "max_testnet_order_count",
    "max_testnet_daily_loss_usd",
    "manual_kill_switch_confirmation",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
)

REQUIRED_TRUE_FIELDS: tuple[str, ...] = (
    "manual_kill_switch_confirmation",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
)

UNSAFE_TRUTHY_FIELDS: tuple[str, ...] = (
    "runtime_permission_source",
    "operator_decision_runtime_authority",
    "stage_transition_authority",
    "executor_enablement_authority",
    "executor_approval_authority",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_executor_approval_authority",
    "signed_testnet_execution_authority",
    "signed_testnet_order_submission_authority",
    "signed_testnet_promotion_authority",
    "actual_stage_transition_performed",
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
    "live_trading_allowed",
    "auto_promotion_allowed",
)

FORBIDDEN_SECRET_FIELD_FRAGMENTS: tuple[str, ...] = (
    "api_key_value",
    "api_secret_value",
    "private_key",
    "secret_value",
    "passphrase",
    "seed_phrase",
    "mnemonic",
)




def _storage_dir(
    cfg: AppConfig,
) -> Path:
    return _common_storage_dir(
        cfg,
        "storage/governance/pre_executor_review",
    )



def _submission_path(
    cfg: AppConfig,
) -> Path:
    path = (
        cfg.root
        / SUBMISSION_RELATIVE_PATH
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path.resolve()


















def _unsafe_true_fields(
    payload: Mapping[str, Any],
) -> list[str]:
    return _common_unsafe_true_fields(
        payload,
        fields=UNSAFE_TRUTHY_FIELDS,
    )







def _source_contract(
    *,
    stage_transition_review: Mapping[
        str,
        Any,
    ],
    phase7_14_report: Mapping[
        str,
        Any,
    ],
    operator_decision_packet: Mapping[
        str,
        Any,
    ],
    operator_decision_guard: Mapping[
        str,
        Any,
    ],
) -> dict[str, Any]:
    return {
        "source_stage_transition_review_id": (
            stage_transition_review.get(
                "stage_transition_review_id"
            )
        ),
        "source_stage_transition_review_hash": (
            _artifact_hash(
                stage_transition_review
            )
        ),
        "source_phase7_14_report_id": (
            phase7_14_report.get(
                "phase7_14_future_executor_"
                "operator_decision_packet_id"
            )
        ),
        "source_phase7_14_report_hash": (
            _artifact_hash(
                phase7_14_report
            )
        ),
        "source_operator_decision_packet_hash": (
            _artifact_hash(
                operator_decision_packet
            )
        ),
        "source_operator_decision_guard_hash": (
            _artifact_hash(
                operator_decision_guard
            )
        ),
    }


def build_operator_decision_intake_template(
    *,
    stage_transition_review: Mapping[
        str,
        Any,
    ],
    phase7_14_report: Mapping[
        str,
        Any,
    ],
    operator_decision_packet: Mapping[
        str,
        Any,
    ],
    operator_decision_guard: Mapping[
        str,
        Any,
    ],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    source = _source_contract(
        stage_transition_review=(
            stage_transition_review
        ),
        phase7_14_report=(
            phase7_14_report
        ),
        operator_decision_packet=(
            operator_decision_packet
        ),
        operator_decision_guard=(
            operator_decision_guard
        ),
    )

    template: dict[
        str,
        Any,
    ] = {
        "template_type": (
            "future_executor_operator_decision_"
            "intake_template_review_only"
        ),
        "pre_executor_review_version": (
            PRE_EXECUTOR_REVIEW_VERSION
        ),
        "review_only": True,
        "template_only": True,
        "not_runtime_authority": True,
        "do_not_write_automatically": True,
        "submission_target_relative_path": (
            SUBMISSION_RELATIVE_PATH
        ),
        "allowed_decision_options": list(
            ALLOWED_DECISION_OPTIONS
        ),
        "required_submission_fields": list(
            REQUIRED_SUBMISSION_FIELDS
        ),
        "operator_decision_id": (
            "MANUAL_REQUIRED_OPERATOR_DECISION_ID"
        ),
        "operator_decision_intake_id": (
            "MANUAL_REQUIRED_OPERATOR_DECISION_INTAKE_ID"
        ),
        "operator_id": (
            "MANUAL_REQUIRED_OPERATOR_ID"
        ),
        "operator_ticket_or_signature": (
            "MANUAL_REQUIRED_TICKET_OR_SIGNATURE_REFERENCE"
        ),
        "canonical_utc_timestamp": (
            "MANUAL_REQUIRED_CANONICAL_UTC_TIMESTAMP"
        ),
        "decision_option": (
            "MANUAL_REQUIRED_DECISION_OPTION"
        ),
        "decision_reason": (
            "MANUAL_REQUIRED_DECISION_REASON"
        ),
        **source,
        "metadata_only_key_reference_id": (
            "MANUAL_REQUIRED_METADATA_ONLY_KEY_REFERENCE_ID"
        ),
        "metadata_only_key_fingerprint": (
            "MANUAL_REQUIRED_METADATA_ONLY_KEY_FINGERPRINT"
        ),
        "max_testnet_notional_usd": (
            "MANUAL_REQUIRED_MAX_TESTNET_NOTIONAL_USD"
        ),
        "max_testnet_order_count": (
            "MANUAL_REQUIRED_MAX_TESTNET_ORDER_COUNT"
        ),
        "max_testnet_daily_loss_usd": (
            "MANUAL_REQUIRED_MAX_TESTNET_DAILY_LOSS_USD"
        ),
        "manual_kill_switch_confirmation": (
            "MANUAL_REQUIRED_TRUE"
        ),
        "hard_caps_rechecked": (
            "MANUAL_REQUIRED_TRUE"
        ),
        "pre_order_risk_gate_rechecked": (
            "MANUAL_REQUIRED_TRUE"
        ),
        "fresh_pre_submit_payload_validation_required": (
            "MANUAL_REQUIRED_TRUE"
        ),
        "fresh_pre_order_risk_gate_recheck_required": (
            "MANUAL_REQUIRED_TRUE"
        ),
        "reconciliation_required_after_any_session": (
            "MANUAL_REQUIRED_TRUE"
        ),
        "session_close_report_required": (
            "MANUAL_REQUIRED_TRUE"
        ),
        "operator_decision_packet_is_operator_decision": False,
        "operator_decision_intake_is_runtime_authority": False,
        "operator_decision_intake_can_enable_executor": False,
        "operator_decision_intake_can_submit_order": False,
        "operator_decision_intake_can_transition_stage": False,
        "phase8_preparation_review_only": True,
        "phase8_execution_allowed": False,
        "actual_operator_decision_recorded": False,
        "actual_stage_transition_performed": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "runtime_permission_source": False,
        "operator_decision_runtime_authority": False,
        "stage_transition_authority": False,
        "executor_enablement_authority": False,
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
        "created_at_utc": (
            created
        ),
    }

    template[
        "operator_decision_intake_template_sha256"
    ] = sha256_json(
        template
    )

    return template


def validate_operator_decision_intake(
    *,
    submission: Mapping[
        str,
        Any,
    ] | None,
    expected_source: Mapping[
        str,
        Any,
    ],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    data = dict(
        submission
        or {}
    )

    actual_submission_present = bool(
        data
    )

    missing: list[str] = []

    placeholders: list[str] = []

    blockers: list[str] = []

    if not actual_submission_present:
        blockers.append(
            "OPERATOR_DECISION_SUBMISSION_MISSING"
        )

    else:
        for field in (
            REQUIRED_SUBMISSION_FIELDS
        ):
            if field not in data:
                missing.append(
                    field
                )

            elif _is_placeholder(
                data.get(
                    field
                )
            ):
                placeholders.append(
                    field
                )

        if missing:
            blockers.append(
                "MISSING_REQUIRED_OPERATOR_DECISION_FIELDS:"
                + ",".join(
                    sorted(
                        missing
                    )
                )
            )

        if placeholders:
            blockers.append(
                "PLACEHOLDER_OPERATOR_DECISION_FIELDS:"
                + ",".join(
                    sorted(
                        placeholders
                    )
                )
            )

        if not _canonical_utc_valid(
            data.get(
                "canonical_utc_timestamp"
            )
        ):
            blockers.append(
                "INVALID_OPERATOR_DECISION_CANONICAL_UTC_TIMESTAMP"
            )

        decision_option = _safe_text(
            data.get(
                "decision_option"
            )
        )

        if (
            decision_option
            not in ALLOWED_DECISION_OPTIONS
        ):
            blockers.append(
                "INVALID_OPERATOR_DECISION_OPTION"
            )

        for field in (
            "source_stage_transition_review_id",
            "source_stage_transition_review_hash",
            "source_phase7_14_report_id",
            "source_phase7_14_report_hash",
            "source_operator_decision_packet_hash",
            "source_operator_decision_guard_hash",
        ):
            if (
                _safe_text(
                    data.get(
                        field
                    )
                )
                != _safe_text(
                    expected_source.get(
                        field
                    )
                )
            ):
                blockers.append(
                    "OPERATOR_DECISION_SOURCE_MISMATCH:"
                    + field
                )

        if not _hex_fingerprint_valid(
            data.get(
                "metadata_only_key_fingerprint"
            )
        ):
            blockers.append(
                "INVALID_METADATA_ONLY_KEY_FINGERPRINT"
            )

        if not _positive_within(
            data.get(
                "max_testnet_notional_usd"
            ),
            MAX_TESTNET_NOTIONAL_USD,
        ):
            blockers.append(
                "MAX_TESTNET_NOTIONAL_INVALID_OR_EXCEEDS_REVIEW_CAP"
            )

        if not _positive_integer_within(
            data.get(
                "max_testnet_order_count"
            ),
            MAX_TESTNET_ORDER_COUNT,
        ):
            blockers.append(
                "MAX_TESTNET_ORDER_COUNT_INVALID_OR_EXCEEDS_REVIEW_CAP"
            )

        if not _positive_within(
            data.get(
                "max_testnet_daily_loss_usd"
            ),
            MAX_TESTNET_DAILY_LOSS_USD,
        ):
            blockers.append(
                "MAX_TESTNET_DAILY_LOSS_INVALID_OR_EXCEEDS_REVIEW_CAP"
            )

        for field in (
            REQUIRED_TRUE_FIELDS
        ):
            if (
                data.get(
                    field
                )
                is not True
            ):
                blockers.append(
                    "REQUIRED_OPERATOR_DECISION_CONFIRMATION_NOT_TRUE:"
                    + field
                )

        unsafe = (
            _unsafe_true_fields(
                data
            )
        )

        if unsafe:
            blockers.append(
                "UNSAFE_OPERATOR_DECISION_FLAGS:"
                + ",".join(
                    unsafe
                )
            )

        forbidden_secret_fields = (
            _forbidden_secret_fields(
                data
            )
        )

        if (
            forbidden_secret_fields
        ):
            blockers.append(
                "FORBIDDEN_SECRET_VALUE_FIELDS_PRESENT:"
                + ",".join(
                    forbidden_secret_fields
                )
            )

    blockers = sorted(
        set(
            blockers
        )
    )

    waiting_only = (
        blockers
        == [
            "OPERATOR_DECISION_SUBMISSION_MISSING"
        ]
    )

    valid = (
        actual_submission_present
        and not blockers
    )

    decision_option = _safe_text(
        data.get(
            "decision_option"
        )
    )

    decision_disposition = (
        "APPROVE_PHASE8_PREPARATION_REVIEW_ONLY"
        if (
            valid
            and decision_option
            == APPROVE_OPTION
        )
        else (
            "DEFERRED_REVIEW_ONLY"
            if (
                valid
                and decision_option
                == DEFER_OPTION
            )
            else (
                "REJECTED_REVIEW_ONLY"
                if (
                    valid
                    and decision_option
                    == REJECT_OPTION
                )
                else (
                    "WAITING_FOR_OPERATOR_DECISION"
                    if waiting_only
                    else "INVALID_OR_BLOCKED"
                )
            )
        )
    )

    validation: dict[
        str,
        Any,
    ] = {
        "operator_decision_intake_validation_id": (
            stable_id(
                "operator_decision_intake_validation",
                {
                    "source": (
                        expected_source
                    ),
                    "submission_hash": (
                        sha256_json(
                            data
                        )
                        if data
                        else None
                    ),
                    "created_at_utc": (
                        created
                    ),
                },
                24,
            )
        ),
        "validation_type": (
            "future_executor_operator_decision_"
            "intake_validation_review_only"
        ),
        "pre_executor_review_version": (
            PRE_EXECUTOR_REVIEW_VERSION
        ),
        "review_only": True,
        "not_runtime_authority": True,
        "actual_operator_submission_present": (
            actual_submission_present
        ),
        "actual_operator_decision_recorded": (
            valid
        ),
        "operator_decision_intake_validated": (
            valid
        ),
        "waiting_for_operator_decision": (
            waiting_only
        ),
        "blocked": (
            not valid
            and not waiting_only
        ),
        "fail_closed": (
            not valid
            and not waiting_only
        ),
        "decision_option": (
            decision_option
            if valid
            else None
        ),
        "decision_disposition": (
            decision_disposition
        ),
        "missing_required_fields": (
            sorted(
                missing
            )
        ),
        "placeholder_fields": (
            sorted(
                placeholders
            )
        ),
        "blockers": (
            blockers
        ),
        "submission_sha256": (
            sha256_json(
                data
            )
            if data
            else None
        ),
        "operator_decision_runtime_authority": False,
        "operator_decision_intake_is_runtime_authority": False,
        "actual_stage_transition_performed": False,
        "stage_transition_authority": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "phase8_preparation_review_allowed": (
            valid
            and decision_option
            == APPROVE_OPTION
        ),
        "phase8_execution_allowed": False,
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
        "created_at_utc": (
            created
        ),
    }

    validation[
        "operator_decision_intake_validation_sha256"
    ] = sha256_json(
        validation
    )

    return validation


def build_final_pre_executor_review_packet(
    *,
    intake_template: Mapping[
        str,
        Any,
    ],
    intake_validation: Mapping[
        str,
        Any,
    ],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    waiting = (
        intake_validation.get(
            "waiting_for_operator_decision"
        )
        is True
    )

    valid = (
        intake_validation.get(
            "operator_decision_intake_validated"
        )
        is True
    )

    decision_option = _safe_text(
        intake_validation.get(
            "decision_option"
        )
    )

    blocked = (
        intake_validation.get(
            "blocked"
        )
        is True
    )

    if waiting:
        state = (
            STATE_WAITING_FOR_OPERATOR_DECISION
        )

        status = (
            STATUS_WAITING_REVIEW_ONLY
        )

        next_action = (
            "complete_manual_operator_decision_"
            "intake_without_enabling_execution"
        )

    elif (
        valid
        and decision_option
        == APPROVE_OPTION
    ):
        state = (
            STATE_OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY
        )

        status = (
            STATUS_APPROVED_REVIEW_ONLY
        )

        next_action = (
            "begin_phase8_execution_preparation_"
            "design_review_only_keep_submission_disabled"
        )

    elif (
        valid
        and decision_option
        == DEFER_OPTION
    ):
        state = (
            STATE_OPERATOR_DECISION_DEFERRED_REVIEW_ONLY
        )

        status = (
            STATUS_DEFERRED_REVIEW_ONLY
        )

        next_action = (
            "hold_phase8_preparation_until_"
            "new_operator_decision_intake"
        )

    elif (
        valid
        and decision_option
        == REJECT_OPTION
    ):
        state = (
            STATE_OPERATOR_DECISION_REJECTED_REVIEW_ONLY
        )

        status = (
            STATUS_REJECTED_REVIEW_ONLY
        )

        next_action = (
            "stop_phase8_preparation_and_"
            "preserve_disabled_executor_state"
        )

    else:
        state = (
            STATE_BLOCKED
        )

        status = (
            STATUS_BLOCKED_REVIEW_ONLY
        )

        next_action = (
            "resolve_operator_decision_intake_"
            "validation_blockers"
        )

    final_ready = (
        state
        == (
            STATE_OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY
        )
    )

    packet: dict[
        str,
        Any,
    ] = {
        "final_pre_executor_review_packet_id": (
            stable_id(
                "final_pre_executor_review_packet",
                {
                    "template_hash": (
                        _artifact_hash(
                            intake_template
                        )
                    ),
                    "validation_hash": (
                        _artifact_hash(
                            intake_validation
                        )
                    ),
                    "state": (
                        state
                    ),
                    "created_at_utc": (
                        created
                    ),
                },
                24,
            )
        ),
        "packet_type": (
            "final_pre_executor_review_packet_review_only"
        ),
        "pre_executor_review_version": (
            PRE_EXECUTOR_REVIEW_VERSION
        ),
        "status": (
            status
        ),
        "pre_executor_review_state": (
            state
        ),
        "review_only": True,
        "final_pre_executor_review_only": True,
        "not_runtime_authority": True,
        "blocked": (
            blocked
            or state
            == STATE_BLOCKED
        ),
        "fail_closed": (
            blocked
            or state
            == STATE_BLOCKED
        ),
        "waiting_for_operator_decision": (
            waiting
        ),
        "operator_decision_intake_validated": (
            valid
        ),
        "actual_operator_decision_recorded": (
            valid
        ),
        "decision_option": (
            decision_option
            if valid
            else None
        ),
        "decision_disposition": (
            intake_validation.get(
                "decision_disposition"
            )
        ),
        "final_pre_executor_review_ready": (
            final_ready
        ),
        "phase8_preparation_design_review_allowed": (
            final_ready
        ),
        "phase8_preparation_review_only": True,
        "phase8_execution_allowed": False,
        "phase8_write_path_allowed": False,
        "phase8_secret_value_handling_allowed": False,
        "phase8_executor_enablement_allowed": False,
        "phase8_order_submission_allowed": False,
        "operator_decision_is_runtime_authority": False,
        "operator_decision_can_transition_stage": False,
        "operator_decision_can_enable_executor": False,
        "operator_decision_can_submit_order": False,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "metadata_only_key_reference_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "source_operator_decision_intake_template_hash": (
            _artifact_hash(
                intake_template
            )
        ),
        "source_operator_decision_intake_validation_hash": (
            _artifact_hash(
                intake_validation
            )
        ),
        "blockers": (
            list(
                intake_validation.get(
                    "blockers"
                )
                or []
            )
        ),
        "next_action": (
            next_action
        ),
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
        "actual_stage_transition_performed": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
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
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": (
            created
        ),
    }

    packet[
        "final_pre_executor_review_packet_sha256"
    ] = sha256_json(
        packet
    )

    return packet


def build_pre_executor_review_report(
    *,
    stage_transition_review: Mapping[
        str,
        Any,
    ],
    phase7_14_report: Mapping[
        str,
        Any,
    ],
    operator_decision_packet: Mapping[
        str,
        Any,
    ],
    operator_decision_guard: Mapping[
        str,
        Any,
    ],
    intake_template: Mapping[
        str,
        Any,
    ],
    intake_validation: Mapping[
        str,
        Any,
    ],
    final_packet: Mapping[
        str,
        Any,
    ],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    source_artifacts = {
        "stage_transition_review": dict(
            stage_transition_review
            or {}
        ),
        "phase7_14_report": dict(
            phase7_14_report
            or {}
        ),
        "operator_decision_packet": dict(
            operator_decision_packet
            or {}
        ),
        "operator_decision_guard": dict(
            operator_decision_guard
            or {}
        ),
    }

    missing = sorted(
        name
        for (
            name,
            payload,
        ) in source_artifacts.items()
        if not payload
    )

    unsafe_by_source = {
        name: (
            _unsafe_true_fields(
                payload
            )
        )
        for (
            name,
            payload,
        ) in source_artifacts.items()
        if (
            _unsafe_true_fields(
                payload
            )
        )
    }

    structural_blockers: list[str] = []

    if missing:
        structural_blockers.append(
            "MISSING_PRE_EXECUTOR_SOURCE_ARTIFACTS:"
            + ",".join(
                missing
            )
        )

    if unsafe_by_source:
        structural_blockers.append(
            "UNSAFE_PRE_EXECUTOR_SOURCE_FLAGS"
        )

    if (
        stage_transition_review.get(
            "stage_transition_review_state"
        )
        != (
            "OPERATOR_DECISION_PACKET_REVIEW_ONLY"
        )
    ):
        structural_blockers.append(
            "STAGE_TRANSITION_REVIEW_NOT_READY"
        )

    if (
        stage_transition_review.get(
            "operator_decision_packet_ready"
        )
        is not True
    ):
        structural_blockers.append(
            "OPERATOR_DECISION_PACKET_NOT_READY"
        )

    if (
        stage_transition_review.get(
            "operator_decision_packet_is_runtime_authority"
        )
        is not False
    ):
        structural_blockers.append(
            "OPERATOR_DECISION_PACKET_RUNTIME_AUTHORITY_INVALID"
        )

    if (
        phase7_14_report.get(
            "phase7_14_operator_decision_packet_ready"
        )
        is not True
    ):
        structural_blockers.append(
            "PHASE7_14_OPERATOR_DECISION_PACKET_NOT_READY"
        )

    if (
        operator_decision_guard.get(
            "guard_passed"
        )
        is not True
    ):
        structural_blockers.append(
            "PHASE7_14_OPERATOR_DECISION_GUARD_NOT_PASSED"
        )

    final_state = _safe_text(
        final_packet.get(
            "pre_executor_review_state"
        )
    )

    final_blocked = (
        final_packet.get(
            "blocked"
        )
        is True
    )

    blockers = sorted(
        set(
            structural_blockers
            + list(
                final_packet.get(
                    "blockers"
                )
                or []
            )
        )
    )

    if structural_blockers:
        state = (
            STATE_BLOCKED
        )

        status = (
            STATUS_BLOCKED_REVIEW_ONLY
        )

        blocked = True

        fail_closed = True

    else:
        state = (
            final_state
        )

        status = _safe_text(
            final_packet.get(
                "status"
            )
        )

        blocked = (
            final_blocked
        )

        fail_closed = (
            final_packet.get(
                "fail_closed"
            )
            is True
        )

    report: dict[
        str,
        Any,
    ] = {
        "pre_executor_review_id": (
            stable_id(
                "pre_executor_review",
                {
                    "stage_transition_hash": (
                        _artifact_hash(
                            stage_transition_review
                        )
                    ),
                    "phase7_14_hash": (
                        _artifact_hash(
                            phase7_14_report
                        )
                    ),
                    "template_hash": (
                        _artifact_hash(
                            intake_template
                        )
                    ),
                    "validation_hash": (
                        _artifact_hash(
                            intake_validation
                        )
                    ),
                    "final_packet_hash": (
                        _artifact_hash(
                            final_packet
                        )
                    ),
                    "state": (
                        state
                    ),
                    "created_at_utc": (
                        created
                    ),
                },
                24,
            )
        ),
        "pre_executor_review_version": (
            PRE_EXECUTOR_REVIEW_VERSION
        ),
        "status": (
            status
        ),
        "pre_executor_review_state": (
            state
        ),
        "review_only": True,
        "pre_executor_review_only": True,
        "not_runtime_authority": True,
        "blocked": (
            blocked
        ),
        "fail_closed": (
            fail_closed
        ),
        "waiting_for_operator_decision": (
            final_packet.get(
                "waiting_for_operator_decision"
            )
            is True
        ),
        "operator_decision_intake_template_created": True,
        "operator_decision_intake_submission_written_automatically": False,
        "operator_decision_intake_validated": (
            intake_validation.get(
                "operator_decision_intake_validated"
            )
            is True
        ),
        "actual_operator_submission_present": (
            intake_validation.get(
                "actual_operator_submission_present"
            )
            is True
        ),
        "actual_operator_decision_recorded": (
            intake_validation.get(
                "actual_operator_decision_recorded"
            )
            is True
        ),
        "decision_option": (
            intake_validation.get(
                "decision_option"
            )
        ),
        "decision_disposition": (
            intake_validation.get(
                "decision_disposition"
            )
        ),
        "final_pre_executor_review_packet_created": True,
        "final_pre_executor_review_ready": (
            final_packet.get(
                "final_pre_executor_review_ready"
            )
            is True
        ),
        "phase8_preparation_design_review_allowed": (
            final_packet.get(
                "phase8_preparation_design_review_allowed"
            )
            is True
        ),
        "phase8_execution_allowed": False,
        "phase8_write_path_allowed": False,
        "phase8_secret_value_handling_allowed": False,
        "phase8_executor_enablement_allowed": False,
        "phase8_order_submission_allowed": False,
        "operator_decision_is_runtime_authority": False,
        "operator_decision_can_transition_stage": False,
        "operator_decision_can_enable_executor": False,
        "operator_decision_can_submit_order": False,
        "source_artifact_hashes": {
            name: (
                _artifact_hash(
                    payload
                )
            )
            for (
                name,
                payload,
            ) in source_artifacts.items()
        },
        "missing_source_artifacts": (
            missing
        ),
        "unsafe_flags_by_source": (
            unsafe_by_source
        ),
        "blockers": (
            blockers
        ),
        "next_action": (
            final_packet.get(
                "next_action"
            )
            if not structural_blockers
            else (
                "resolve_pre_executor_source_"
                "artifact_or_safety_blockers"
            )
        ),
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
        "actual_stage_transition_performed": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
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
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": (
            created
        ),
    }

    report[
        "pre_executor_review_sha256"
    ] = sha256_json(
        report
    )

    return report


def run_pre_executor_review_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    run_stage_transition_first: bool = True,
    stage_transition_runner: Callable[
        ...,
        Mapping[
            str,
            Any,
        ],
    ] | None = None,
    submission_override: Mapping[
        str,
        Any,
    ] | None = None,
) -> dict[str, Any]:
    """Run Phase 7.15-7.17 as one manual-intake review chain."""

    cfg = (
        cfg
        or load_config(
            project_root
        )
    )

    if (
        run_stage_transition_first
    ):
        if (
            stage_transition_runner
            is None
        ):
            from crypto_ai_system.governance.stage_transition import (
                run_stage_transition_chain,
            )

            stage_transition_runner = (
                run_stage_transition_chain
            )

        stage_transition_runner(
            cfg=cfg
        )

    latest = _latest_dir(
        cfg
    )

    stage_transition_review = dict(
        read_json(
            latest
            / "stage_transition_review_report.json",
            default={},
        )
        or {}
    )

    phase7_14_report = dict(
        read_json(
            latest
            / (
                "phase7_14_future_executor_"
                "operator_decision_packet_report.json"
            ),
            default={},
        )
        or {}
    )

    operator_decision_packet = dict(
        read_json(
            latest
            / (
                "future_signed_testnet_executor_"
                "operator_decision_packet_review_only.json"
            ),
            default={},
        )
        or {}
    )

    operator_decision_guard = dict(
        read_json(
            latest
            / (
                "future_signed_testnet_executor_"
                "operator_decision_guard_report.json"
            ),
            default={},
        )
        or {}
    )

    created = (
        utc_now_canonical()
    )

    intake_template = (
        build_operator_decision_intake_template(
            stage_transition_review=(
                stage_transition_review
            ),
            phase7_14_report=(
                phase7_14_report
            ),
            operator_decision_packet=(
                operator_decision_packet
            ),
            operator_decision_guard=(
                operator_decision_guard
            ),
            created_at_utc=(
                created
            ),
        )
    )

    expected_source = (
        _source_contract(
            stage_transition_review=(
                stage_transition_review
            ),
            phase7_14_report=(
                phase7_14_report
            ),
            operator_decision_packet=(
                operator_decision_packet
            ),
            operator_decision_guard=(
                operator_decision_guard
            ),
        )
    )

    if (
        submission_override
        is not None
    ):
        submission = dict(
            submission_override
        )

    else:
        submission = dict(
            read_json(
                _submission_path(
                    cfg
                ),
                default={},
            )
            or {}
        )

    intake_validation = (
        validate_operator_decision_intake(
            submission=(
                submission
            ),
            expected_source=(
                expected_source
            ),
            created_at_utc=(
                created
            ),
        )
    )

    final_packet = (
        build_final_pre_executor_review_packet(
            intake_template=(
                intake_template
            ),
            intake_validation=(
                intake_validation
            ),
            created_at_utc=(
                created
            ),
        )
    )

    report = (
        build_pre_executor_review_report(
            stage_transition_review=(
                stage_transition_review
            ),
            phase7_14_report=(
                phase7_14_report
            ),
            operator_decision_packet=(
                operator_decision_packet
            ),
            operator_decision_guard=(
                operator_decision_guard
            ),
            intake_template=(
                intake_template
            ),
            intake_validation=(
                intake_validation
            ),
            final_packet=(
                final_packet
            ),
            created_at_utc=(
                created
            ),
        )
    )

    storage = (
        _storage_dir(
            cfg
        )
    )

    artifacts = {
        "operator_decision_intake_template": (
            intake_template
        ),
        "operator_decision_intake_validation": (
            intake_validation
        ),
        "final_pre_executor_review_packet": (
            final_packet
        ),
    }

    file_map = {
        "operator_decision_intake_template": (
            "operator_decision_intake_template_review_only.json"
        ),
        "operator_decision_intake_validation": (
            "operator_decision_intake_validation_report.json"
        ),
        "final_pre_executor_review_packet": (
            "final_pre_executor_review_packet_review_only.json"
        ),
    }

    for (
        name,
        payload,
    ) in artifacts.items():
        file_name = (
            file_map[
                name
            ]
        )

        atomic_write_json(
            latest
            / file_name,
            payload,
        )

        atomic_write_json(
            storage
            / file_name,
            payload,
        )

    atomic_write_json(
        latest
        / "pre_executor_review_report.json",
        report,
    )

    atomic_write_json(
        storage
        / "pre_executor_review_report.json",
        report,
    )

    return {
        "report": (
            report
        ),
        "legacy_outputs": (
            artifacts
        ),
    }


def run_pre_executor_review_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return (
        run_pre_executor_review_chain(
            cfg=cfg,
            project_root=(
                project_root
            ),
        )["report"]
    )


__all__ = [
    "PRE_EXECUTOR_REVIEW_VERSION",
    "STATE_WAITING_FOR_OPERATOR_DECISION",
    "STATE_OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY",
    "STATE_OPERATOR_DECISION_DEFERRED_REVIEW_ONLY",
    "STATE_OPERATOR_DECISION_REJECTED_REVIEW_ONLY",
    "STATE_BLOCKED",
    "APPROVE_OPTION",
    "DEFER_OPTION",
    "REJECT_OPTION",
    "ALLOWED_DECISION_OPTIONS",
    "REQUIRED_SUBMISSION_FIELDS",
    "build_operator_decision_intake_template",
    "validate_operator_decision_intake",
    "build_final_pre_executor_review_packet",
    "build_pre_executor_review_report",
    "run_pre_executor_review_chain",
    "run_pre_executor_review_latest",
]
