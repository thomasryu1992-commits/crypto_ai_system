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

STAGE_TRANSITION_REVIEW_VERSION = (
    "lean_stage_transition_review_v1"
)

STATE_OPERATOR_DECISION_PACKET_REVIEW_ONLY = (
    "OPERATOR_DECISION_PACKET_REVIEW_ONLY"
)

STATE_STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED = (
    "STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED"
)

STATE_BLOCKED = "BLOCKED"

STATUS_RECORDED_REVIEW_ONLY = (
    "STAGE_TRANSITION_OPERATOR_DECISION_PACKET_"
    "RECORDED_REVIEW_ONLY"
)

STATUS_REPAIR_REQUIRED_REVIEW_ONLY = (
    "STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED_"
    "REVIEW_ONLY"
)

STATUS_BLOCKED_REVIEW_ONLY = (
    "STAGE_TRANSITION_REVIEW_BLOCKED_REVIEW_ONLY"
)

_UNSAFE_FIELDS: tuple[str, ...] = (
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
    "actual_operator_decision_recorded",
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

_COMPONENT_SPECS: tuple[
    tuple[str, str, str],
    ...,
] = (
    (
        "enablement_design_review",
        "phase7_11_future_executor_enablement_"
        "design_review_id",
        "phase7_11_report_sha256",
    ),
    (
        "enablement_guard_fixture",
        "phase7_12_future_executor_enablement_"
        "guard_fixture_id",
        "phase7_12_report_sha256",
    ),
    (
        "enablement_review_packet",
        "phase7_13_future_executor_enablement_"
        "review_packet_id",
        "phase7_13_report_sha256",
    ),
    (
        "operator_decision_packet",
        "phase7_14_future_executor_operator_"
        "decision_packet_id",
        "phase7_14_report_sha256",
    ),
)




def _storage_dir(
    cfg: AppConfig,
) -> Path:
    return _common_storage_dir(
        cfg,
        "storage/governance/stage_transition",
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
    payload: Mapping[
        str,
        Any,
    ] | None,
    id_field: str,
    hash_field: str,
) -> dict[str, Any]:
    source = dict(
        payload
        or {}
    )

    return {
        "component": name,
        "source_id": (
            source.get(
                id_field
            )
        ),
        "source_sha256": (
            source.get(
                hash_field
            )
        ),
        "status": (
            source.get(
                "status"
            )
        ),
        "blocked": (
            source.get(
                "blocked"
            )
            is True
        ),
        "fail_closed": (
            source.get(
                "fail_closed"
            )
            is True
        ),
        "review_only": (
            source.get(
                "review_only"
            )
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
        Mapping[
            str,
            Any,
        ],
    ],
    components: Mapping[
        str,
        Mapping[
            str,
            Any,
        ],
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
                "STAGE_TRANSITION_COMPONENT_MISSING:"
                + name
            )

            continue

        if not projection.get(
            "source_id"
        ):
            blockers.append(
                "STAGE_TRANSITION_COMPONENT_ID_MISSING:"
                + name
            )

        if not projection.get(
            "source_sha256"
        ):
            blockers.append(
                "STAGE_TRANSITION_COMPONENT_HASH_MISSING:"
                + name
            )

        if not projection.get(
            "status"
        ):
            blockers.append(
                "STAGE_TRANSITION_COMPONENT_STATUS_MISSING:"
                + name
            )

        if projection.get(
            "unsafe_true_flags"
        ):
            blockers.append(
                "STAGE_TRANSITION_COMPONENT_UNSAFE_FLAG:"
                + name
            )

    return blockers


def build_stage_transition_review_report(
    *,
    legacy_outputs: Mapping[
        str,
        Mapping[
            str,
            Any,
        ],
    ],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    components = {
        name: (
            _component_projection(
                name=name,
                payload=(
                    legacy_outputs.get(
                        name
                    )
                ),
                id_field=(
                    id_field
                ),
                hash_field=(
                    hash_field
                ),
            )
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
            components=(
                components
            ),
        )
    )

    design = dict(
        legacy_outputs.get(
            "enablement_design_review"
        )
        or {}
    )

    fixture = dict(
        legacy_outputs.get(
            "enablement_guard_fixture"
        )
        or {}
    )

    review = dict(
        legacy_outputs.get(
            "enablement_review_packet"
        )
        or {}
    )

    decision = dict(
        legacy_outputs.get(
            "operator_decision_packet"
        )
        or {}
    )

    sources = (
        design,
        fixture,
        review,
        decision,
    )

    source_actual_operator_decision_recorded = any(
        source.get(
            "actual_operator_decision_recorded"
        )
        is True
        for source in sources
    )

    source_actual_stage_transition_performed = any(
        source.get(
            "actual_stage_transition_performed"
        )
        is True
        for source in sources
    )

    source_actual_executor_approval_created = any(
        source.get(
            "actual_executor_approval_created"
        )
        is True
        for source in sources
    )

    source_actual_executor_enablement_performed = any(
        source.get(
            "actual_executor_enablement_performed"
        )
        is True
        for source in sources
    )

    source_actual_order_submission_performed = any(
        source.get(
            "actual_order_submission_performed"
        )
        is True
        for source in sources
    )

    source_actual_cancel_performed = any(
        source.get(
            "actual_cancel_performed"
        )
        is True
        for source in sources
    )

    source_external_order_submission_performed = any(
        source.get(
            "external_order_submission_performed"
        )
        is True
        for source in sources
    )

    source_exchange_endpoint_called = any(
        source.get(
            "exchange_endpoint_called"
        )
        is True
        for source in sources
    )

    source_secret_value_or_file_access_detected = any(
        (
            source.get(
                "secret_value_accessed"
            )
            is True
        )
        or (
            source.get(
                "secret_file_read"
            )
            is True
        )
        or (
            source.get(
                "secret_file_created"
            )
            is True
        )
        for source in sources
    )

    design_ready = (
        design.get(
            "status"
        )
        == (
            "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_"
            "DESIGN_REVIEW_RECORDED_REVIEW_ONLY"
        )
        and design.get(
            "phase7_11_enablement_design_ready"
        )
        is True
        and design.get(
            "future_executor_enablement_"
            "design_packet_created"
        )
        is True
        and design.get(
            "future_executor_enablement_"
            "design_guard_created"
        )
        is True
        and design.get(
            "enablement_design_guard_passed"
        )
        is True
        and design.get(
            "phase7_10_review_packet_ready"
        )
        is True
        and design.get(
            "approval_review_guard_passed"
        )
        is True
        and design.get(
            "metadata_only_key_reference_"
            "validated_review_only"
        )
        is True
        and design.get(
            "prerequisite_packet_hash_matches"
        )
        is True
        and design.get(
            "future_executor_approval_intake_"
            "validated_review_only"
        )
        is True
        and design.get(
            "future_explicit_executor_"
            "enablement_review_required"
        )
        is True
        and design.get(
            "actual_executor_approval_created"
        )
        is False
        and design.get(
            "actual_executor_enablement_performed"
        )
        is False
        and design.get(
            "actual_order_submission_performed"
        )
        is False
        and design.get(
            "external_order_submission_performed"
        )
        is False
        and design.get(
            "exchange_endpoint_called"
        )
        is False
        and design.get(
            "blocked"
        )
        is False
    )

    fixture_ready = (
        fixture.get(
            "status"
        )
        == (
            "PHASE7_12_FUTURE_EXECUTOR_ENABLEMENT_"
            "GUARD_FIXTURE_RECORDED_REVIEW_ONLY"
        )
        and fixture.get(
            "phase7_12_guard_fixture_ready"
        )
        is True
        and fixture.get(
            "valid_enablement_guard_fixture_"
            "passed_review_only_validation"
        )
        is True
        and fixture.get(
            "invalid_enablement_guard_fixtures_"
            "blocked_fail_closed"
        )
        is True
        and fixture.get(
            "enablement_guard_fixture_guard_passed"
        )
        is True
        and fixture.get(
            "actual_executor_enablement_performed"
        )
        is False
        and fixture.get(
            "actual_order_submission_performed"
        )
        is False
        and fixture.get(
            "external_order_submission_performed"
        )
        is False
        and fixture.get(
            "exchange_endpoint_called"
        )
        is False
        and fixture.get(
            "blocked"
        )
        is False
    )

    review_ready = (
        review.get(
            "status"
        )
        == (
            "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_"
            "REVIEW_PACKET_RECORDED_REVIEW_ONLY"
        )
        and review.get(
            "phase7_13_review_packet_ready"
        )
        is True
        and review.get(
            "future_executor_enablement_"
            "review_packet_created"
        )
        is True
        and review.get(
            "future_executor_enablement_"
            "review_guard_report_created"
        )
        is True
        and review.get(
            "enablement_review_guard_passed"
        )
        is True
        and review.get(
            "future_executor_enablement_review_"
            "required_before_any_order"
        )
        is True
        and review.get(
            "actual_executor_enablement_performed"
        )
        is False
        and review.get(
            "actual_order_submission_performed"
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

    decision_ready = (
        decision.get(
            "status"
        )
        == (
            "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_"
            "DECISION_PACKET_RECORDED_REVIEW_ONLY"
        )
        and decision.get(
            "phase7_14_operator_decision_packet_ready"
        )
        is True
        and decision.get(
            "future_executor_operator_"
            "decision_packet_created"
        )
        is True
        and decision.get(
            "future_executor_operator_"
            "decision_guard_report_created"
        )
        is True
        and decision.get(
            "operator_decision_guard_passed"
        )
        is True
        and decision.get(
            "future_operator_decision_"
            "required_before_any_order"
        )
        is True
        and decision.get(
            "actual_operator_decision_recorded"
        )
        is False
        and decision.get(
            "actual_executor_approval_created"
        )
        is False
        and decision.get(
            "actual_executor_enablement_performed"
        )
        is False
        and decision.get(
            "actual_order_submission_performed"
        )
        is False
        and decision.get(
            "external_order_submission_performed"
        )
        is False
        and decision.get(
            "exchange_endpoint_called"
        )
        is False
        and decision.get(
            "blocked"
        )
        is False
    )

    evidence_blockers: list[str] = []

    if not design_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_ENABLEMENT_"
            "DESIGN_REVIEW_NOT_READY"
        )

    if not fixture_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_ENABLEMENT_"
            "GUARD_FIXTURE_NOT_READY"
        )

    if not review_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_ENABLEMENT_"
            "REVIEW_PACKET_NOT_READY"
        )

    if not decision_ready:
        evidence_blockers.append(
            "FUTURE_EXECUTOR_OPERATOR_"
            "DECISION_PACKET_NOT_READY"
        )

    safety_blockers: list[str] = []

    if (
        source_actual_operator_decision_recorded
    ):
        safety_blockers.append(
            "ACTUAL_OPERATOR_DECISION_RECORDED_UNEXPECTEDLY"
        )

    if (
        source_actual_stage_transition_performed
    ):
        safety_blockers.append(
            "ACTUAL_STAGE_TRANSITION_PERFORMED_UNEXPECTEDLY"
        )

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
        source_secret_value_or_file_access_detected
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
        state = (
            STATE_OPERATOR_DECISION_PACKET_REVIEW_ONLY
        )

        status = (
            STATUS_RECORDED_REVIEW_ONLY
        )

        next_action = (
            "prepare_phase7_15_operator_decision_"
            "intake_template_keep_execution_disabled"
        )

    elif (
        structural_blockers
        or safety_blockers
    ):
        state = (
            STATE_BLOCKED
        )

        status = (
            STATUS_BLOCKED_REVIEW_ONLY
        )

        next_action = (
            "resolve_stage_transition_"
            "structural_or_safety_blockers"
        )

    else:
        state = (
            STATE_STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED
        )

        status = (
            STATUS_REPAIR_REQUIRED_REVIEW_ONLY
        )

        next_action = (
            "repair_enablement_or_operator_"
            "decision_packet_evidence_and_rerun"
        )

    seed = {
        "version": (
            STAGE_TRANSITION_REVIEW_VERSION
        ),
        "state": state,
        "component_ids": {
            name: (
                projection.get(
                    "source_id"
                )
            )
            for (
                name,
                projection,
            ) in components.items()
        },
        "created_at_utc": (
            created
        ),
    }

    report: dict[str, Any] = {
        "stage_transition_review_id": (
            stable_id(
                "stage_transition_review",
                seed,
                24,
            )
        ),
        "stage_transition_review_version": (
            STAGE_TRANSITION_REVIEW_VERSION
        ),
        "status": status,
        "stage_transition_review_state": (
            state
        ),
        "blocked": bool(
            blockers
        ),
        "fail_closed": bool(
            blockers
        ),
        "review_only": True,
        "stage_transition_review_only": True,
        "operator_decision_packet_ready": (
            decision_ready
        ),
        "operator_decision_packet_is_operator_decision": False,
        "operator_decision_packet_is_runtime_authority": False,
        "operator_decision_packet_can_enable_executor": False,
        "operator_decision_packet_can_submit_order": False,
        "operator_decision_packet_can_transition_stage": False,
        "phase7_15_operator_decision_intake_required": True,
        "actual_operator_decision_recorded": (
            source_actual_operator_decision_recorded
        ),
        "operator_decision_runtime_authority": False,
        "actual_stage_transition_performed": (
            source_actual_stage_transition_performed
        ),
        "stage_transition_authority": False,
        "future_executor_enablement_design_ready": (
            design_ready
        ),
        "future_executor_enablement_guard_fixture_ready": (
            fixture_ready
        ),
        "future_executor_enablement_review_packet_ready": (
            review_ready
        ),
        "future_executor_operator_decision_packet_ready": (
            decision_ready
        ),
        "future_operator_decision_required_before_any_order": True,
        "future_executor_enablement_review_required_before_any_order": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "metadata_only_key_reference_required": True,
        "hard_caps_rechecked": True,
        "pre_order_risk_gate_rechecked": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "components": (
            components
        ),
        "blockers": (
            blockers
        ),
        "next_action": (
            next_action
        ),
        "source_actual_operator_decision_recorded": (
            source_actual_operator_decision_recorded
        ),
        "source_actual_stage_transition_performed": (
            source_actual_stage_transition_performed
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
            source_secret_value_or_file_access_detected
        ),
        "runtime_permission_source": False,
        "executor_approval_authority": False,
        "executor_enablement_authority": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "actual_executor_approval_created": (
            source_actual_executor_approval_created
        ),
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
            source_secret_value_or_file_access_detected
        ),
        "secret_file_read": (
            source_secret_value_or_file_access_detected
        ),
        "secret_file_created": (
            source_secret_value_or_file_access_detected
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
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": (
            created
        ),
    }

    report[
        "stage_transition_review_sha256"
    ] = sha256_json(
        report
    )

    return report


def run_stage_transition_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    run_executor_approval_first: bool = True,
    executor_approval_runner: Callable[
        ...,
        Mapping[
            str,
            Any,
        ],
    ] | None = None,
    design_runner: Callable[
        ...,
        Mapping[
            str,
            Any,
        ],
    ] | None = None,
    fixture_runner: Callable[
        ...,
        Mapping[
            str,
            Any,
        ],
    ] | None = None,
    review_runner: Callable[
        ...,
        Mapping[
            str,
            Any,
        ],
    ] | None = None,
    decision_runner: Callable[
        ...,
        Mapping[
            str,
            Any,
        ],
    ] | None = None,
) -> dict[str, Any]:
    """Run Phase 7.11-7.14 behind one review-only semantic entry point."""

    cfg = (
        cfg
        or load_config(
            project_root
        )
    )

    if (
        run_executor_approval_first
    ):
        if (
            executor_approval_runner
            is None
        ):
            from crypto_ai_system.governance.executor_approval import (
                run_executor_approval_chain,
            )

            executor_approval_runner = (
                run_executor_approval_chain
            )

        executor_approval_runner(
            cfg=cfg
        )

    if (
        design_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.enablement_design import (
            persist_phase7_11_future_executor_enablement_design_review_report,
        )

        design_runner = (
            persist_phase7_11_future_executor_enablement_design_review_report
        )

    if (
        fixture_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.enablement_guard_fixtures import (
            persist_phase7_12_future_executor_enablement_guard_fixture_report,
        )

        fixture_runner = (
            persist_phase7_12_future_executor_enablement_guard_fixture_report
        )

    if (
        review_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.enablement_review import (
            persist_phase7_13_future_executor_enablement_review_packet_report,
        )

        review_runner = (
            persist_phase7_13_future_executor_enablement_review_packet_report
        )

    if (
        decision_runner
        is None
    ):
        from crypto_ai_system.governance.phase7_steps.operator_decision_packet import (
            persist_phase7_14_future_executor_operator_decision_packet_report,
        )

        decision_runner = (
            persist_phase7_14_future_executor_operator_decision_packet_report
        )

    design = dict(
        design_runner(
            cfg=cfg,
            run_phase7_10_first=False,
        )
    )

    fixture = dict(
        fixture_runner(
            cfg=cfg,
            run_phase7_11_first=False,
        )
    )

    review = dict(
        review_runner(
            cfg=cfg,
            run_phase7_12_first=False,
        )
    )

    decision = dict(
        decision_runner(
            cfg=cfg,
            run_phase7_13_first=False,
        )
    )

    legacy_outputs = {
        "enablement_design_review": (
            design
        ),
        "enablement_guard_fixture": (
            fixture
        ),
        "enablement_review_packet": (
            review
        ),
        "operator_decision_packet": (
            decision
        ),
    }

    report = (
        build_stage_transition_review_report(
            legacy_outputs=(
                legacy_outputs
            ),
        )
    )

    latest = (
        _latest_dir(
            cfg
        )
    )

    storage = (
        _storage_dir(
            cfg
        )
    )

    atomic_write_json(
        latest
        / "stage_transition_review_report.json",
        report,
    )

    atomic_write_json(
        storage
        / "stage_transition_review_report.json",
        report,
    )

    return {
        "report": (
            report
        ),
        "legacy_outputs": (
            legacy_outputs
        ),
    }


def run_stage_transition_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return (
        run_stage_transition_chain(
            cfg=cfg,
            project_root=(
                project_root
            ),
        )["report"]
    )


__all__ = [
    "STAGE_TRANSITION_REVIEW_VERSION",
    "STATE_OPERATOR_DECISION_PACKET_REVIEW_ONLY",
    "STATE_STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED",
    "STATE_BLOCKED",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_REPAIR_REQUIRED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_stage_transition_review_report",
    "run_stage_transition_chain",
    "run_stage_transition_latest",
]
