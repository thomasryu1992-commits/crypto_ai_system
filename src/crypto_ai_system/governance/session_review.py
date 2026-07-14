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
    is_zero_number as _is_zero,
    latest_dir as _latest_dir,
    number_value as _number,
    storage_dir as _common_storage_dir,
    unsafe_true_fields as _common_unsafe_true_fields,
)

SESSION_REVIEW_VERSION = "lean_session_review_v1"

STATE_DISABLED_SESSION_REVIEW_ONLY = (
    "DISABLED_SESSION_REVIEW_ONLY"
)
STATE_SESSION_EVIDENCE_REPAIR_REQUIRED = (
    "SESSION_EVIDENCE_REPAIR_REQUIRED"
)
STATE_BLOCKED = "BLOCKED"

STATUS_RECORDED_REVIEW_ONLY = (
    "SESSION_REVIEW_DISABLED_EVIDENCE_RECORDED_REVIEW_ONLY"
)
STATUS_REPAIR_REQUIRED_REVIEW_ONLY = (
    "SESSION_REVIEW_EVIDENCE_REPAIR_REQUIRED_REVIEW_ONLY"
)
STATUS_BLOCKED_REVIEW_ONLY = (
    "SESSION_REVIEW_BLOCKED_REVIEW_ONLY"
)

_UNSAFE_FIELDS: tuple[str, ...] = (
    "runtime_permission_source",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_reconciliation_authority",
    "signed_testnet_session_close_authority",
    "signed_testnet_promotion_authority",
    "signed_testnet_executor_approval_authority",
    "signed_testnet_execution_authority",
    "signed_testnet_order_submission_authority",
    "actual_reconciliation_authority",
    "actual_session_close_authority",
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
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "auto_promotion_allowed",
)

_COMPONENT_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "disabled_reconciliation_session_close",
        "phase7_4_disabled_execution_reconciliation_session_close_id",
        "phase7_4_report_sha256",
    ),
    (
        "reconciliation_session_close_review_packet",
        "phase7_5_reconciliation_session_close_review_packet_id",
        "phase7_5_report_sha256",
    ),
    (
        "disabled_session_operator_handoff",
        "phase7_6_disabled_signed_testnet_session_operator_handoff_id",
        "phase7_6_report_sha256",
    ),
)




def _storage_dir(
    cfg: AppConfig,
) -> Path:
    return _common_storage_dir(
        cfg,
        "storage/governance/session_review",
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
    source = dict(payload or {})

    return {
        "component": name,
        "source_id": source.get(id_field),
        "source_sha256": source.get(hash_field),
        "status": source.get("status"),
        "blocked": source.get("blocked") is True,
        "fail_closed": source.get("fail_closed") is True,
        "review_only": source.get("review_only") is True,
        "unsafe_true_flags": _unsafe_true_fields(source),
    }


def _structural_blockers(
    *,
    legacy_outputs: Mapping[str, Mapping[str, Any]],
    components: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []

    for name, _, _ in _COMPONENT_SPECS:
        source = dict(
            legacy_outputs.get(name)
            or {}
        )

        projection = dict(
            components.get(name)
            or {}
        )

        if not source:
            blockers.append(
                f"SESSION_REVIEW_COMPONENT_MISSING:{name}"
            )
            continue

        if not projection.get("source_id"):
            blockers.append(
                f"SESSION_REVIEW_COMPONENT_ID_MISSING:{name}"
            )

        if not projection.get("status"):
            blockers.append(
                f"SESSION_REVIEW_COMPONENT_STATUS_MISSING:{name}"
            )

        if projection.get("unsafe_true_flags"):
            blockers.append(
                f"SESSION_REVIEW_COMPONENT_UNSAFE_FLAG:{name}"
            )

    return blockers


def build_session_review_report(
    *,
    legacy_outputs: Mapping[str, Mapping[str, Any]],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = created_at_utc or utc_now_canonical()

    components = {
        name: _component_projection(
            name=name,
            payload=legacy_outputs.get(name),
            id_field=id_field,
            hash_field=hash_field,
        )
        for name, id_field, hash_field in _COMPONENT_SPECS
    }

    structural_blockers = _structural_blockers(
        legacy_outputs=legacy_outputs,
        components=components,
    )

    reconciliation = dict(
        legacy_outputs.get(
            "disabled_reconciliation_session_close"
        )
        or {}
    )

    review_packet = dict(
        legacy_outputs.get(
            "reconciliation_session_close_review_packet"
        )
        or {}
    )

    handoff = dict(
        legacy_outputs.get(
            "disabled_session_operator_handoff"
        )
        or {}
    )

    source_endpoint_call_detected = any(
        source.get("exchange_endpoint_called") is True
        for source in (
            reconciliation,
            review_packet,
            handoff,
        )
    )

    source_external_submission_detected = any(
        source.get(
            "external_order_submission_performed"
        )
        is True
        for source in (
            reconciliation,
            review_packet,
            handoff,
        )
    )

    source_actual_submission_detected = any(
        source.get(
            "actual_order_submission_performed"
        )
        is True
        for source in (
            reconciliation,
            review_packet,
            handoff,
        )
    )

    source_actual_cancel_detected = any(
        source.get("actual_cancel_performed")
        is True
        for source in (
            reconciliation,
            review_packet,
            handoff,
        )
    )

    source_mismatch_detected = any(
        source.get("reconciliation_mismatch")
        is True
        for source in (
            reconciliation,
            review_packet,
            handoff,
        )
    )

    observed_fill_count = (
        reconciliation.get("observed_fill_count")
    )

    observed_position_delta = (
        reconciliation.get("observed_position_delta")
    )

    observed_balance_delta = (
        reconciliation.get("observed_balance_delta")
    )

    zero_effect_evidence = (
        _is_zero(observed_fill_count)
        and _is_zero(observed_position_delta)
        and _is_zero(observed_balance_delta)
    )

    phase7_4_ready = (
        reconciliation.get("status")
        == (
            "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_"
            "SESSION_CLOSE_RECORDED_REVIEW_ONLY"
        )
        and reconciliation.get(
            "phase7_4_reconciliation_session_close_ready"
        )
        is True
        and reconciliation.get(
            "disabled_execution_reconciled_review_only"
        )
        is True
        and reconciliation.get(
            "session_closed_review_only"
        )
        is True
        and reconciliation.get(
            "blocked_execution_evidence_linked"
        )
        is True
        and reconciliation.get(
            "reconciliation_mismatch"
        )
        is False
        and zero_effect_evidence
        and reconciliation.get(
            "actual_executor_enablement_performed"
        )
        is False
        and reconciliation.get(
            "actual_order_submission_performed"
        )
        is False
        and reconciliation.get(
            "actual_cancel_performed"
        )
        is False
        and reconciliation.get(
            "external_order_submission_performed"
        )
        is False
        and reconciliation.get(
            "exchange_endpoint_called"
        )
        is False
        and reconciliation.get("blocked") is False
    )

    phase7_5_ready = (
        review_packet.get("status")
        == (
            "PHASE7_5_RECONCILIATION_SESSION_CLOSE_"
            "REVIEW_PACKET_RECORDED_REVIEW_ONLY"
        )
        and review_packet.get(
            "phase7_5_review_packet_ready"
        )
        is True
        and review_packet.get(
            "promotion_guard_passed"
        )
        is True
        and review_packet.get(
            "disabled_execution_reconciled_review_only"
        )
        is True
        and review_packet.get(
            "session_closed_review_only"
        )
        is True
        and review_packet.get(
            "reconciliation_mismatch"
        )
        is False
        and _is_zero(
            review_packet.get("observed_fill_count")
        )
        and _is_zero(
            review_packet.get("observed_position_delta")
        )
        and _is_zero(
            review_packet.get("observed_balance_delta")
        )
        and review_packet.get(
            "actual_executor_enablement_performed"
        )
        is False
        and review_packet.get(
            "actual_order_submission_performed"
        )
        is False
        and review_packet.get(
            "actual_cancel_performed"
        )
        is False
        and review_packet.get(
            "external_order_submission_performed"
        )
        is False
        and review_packet.get(
            "exchange_endpoint_called"
        )
        is False
        and review_packet.get("blocked") is False
    )

    phase7_6_ready = (
        handoff.get("status")
        == (
            "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_"
            "OPERATOR_HANDOFF_RECORDED_REVIEW_ONLY"
        )
        and handoff.get(
            "phase7_6_operator_handoff_ready"
        )
        is True
        and handoff.get(
            "executor_approval_checklist_ready_review_only"
        )
        is True
        and handoff.get(
            "promotion_guard_passed"
        )
        is True
        and handoff.get(
            "disabled_execution_reconciled_review_only"
        )
        is True
        and handoff.get(
            "session_closed_review_only"
        )
        is True
        and handoff.get(
            "reconciliation_mismatch"
        )
        is False
        and handoff.get(
            "future_executor_approval_required_before_any_order"
        )
        is True
        and handoff.get(
            "actual_executor_enablement_performed"
        )
        is False
        and handoff.get(
            "actual_order_submission_performed"
        )
        is False
        and handoff.get(
            "actual_cancel_performed"
        )
        is False
        and handoff.get(
            "external_order_submission_performed"
        )
        is False
        and handoff.get(
            "exchange_endpoint_called"
        )
        is False
        and handoff.get("blocked") is False
    )

    evidence_blockers: list[str] = []

    if not phase7_4_ready:
        evidence_blockers.append(
            "DISABLED_RECONCILIATION_SESSION_CLOSE_NOT_READY"
        )

    if not phase7_5_ready:
        evidence_blockers.append(
            "RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_NOT_READY"
        )

    if not phase7_6_ready:
        evidence_blockers.append(
            "DISABLED_SESSION_OPERATOR_HANDOFF_NOT_READY"
        )

    if source_mismatch_detected:
        evidence_blockers.append(
            "SESSION_REVIEW_RECONCILIATION_MISMATCH_DETECTED"
        )

    if not zero_effect_evidence:
        evidence_blockers.append(
            "SESSION_REVIEW_NONZERO_OR_INVALID_EFFECT_EVIDENCE"
        )

    safety_blockers: list[str] = []

    if source_endpoint_call_detected:
        safety_blockers.append(
            "SESSION_REVIEW_SOURCE_ENDPOINT_CALL_DETECTED"
        )

    if source_external_submission_detected:
        safety_blockers.append(
            "SESSION_REVIEW_SOURCE_EXTERNAL_SUBMISSION_DETECTED"
        )

    if source_actual_submission_detected:
        safety_blockers.append(
            "SESSION_REVIEW_SOURCE_ACTUAL_SUBMISSION_DETECTED"
        )

    if source_actual_cancel_detected:
        safety_blockers.append(
            "SESSION_REVIEW_SOURCE_ACTUAL_CANCEL_DETECTED"
        )

    blockers = sorted(
        set(
            structural_blockers
            + evidence_blockers
            + safety_blockers
        )
    )

    if not blockers:
        state = STATE_DISABLED_SESSION_REVIEW_ONLY
        status = STATUS_RECORDED_REVIEW_ONLY
        next_action = (
            "prepare_phase7_future_executor_"
            "prerequisite_review_only"
        )
    elif structural_blockers or safety_blockers:
        state = STATE_BLOCKED
        status = STATUS_BLOCKED_REVIEW_ONLY
        next_action = (
            "resolve_session_review_"
            "structural_or_safety_blockers"
        )
    else:
        state = (
            STATE_SESSION_EVIDENCE_REPAIR_REQUIRED
        )
        status = (
            STATUS_REPAIR_REQUIRED_REVIEW_ONLY
        )
        next_action = (
            "repair_reconciliation_or_session_"
            "evidence_and_rerun_review"
        )

    seed = {
        "version": SESSION_REVIEW_VERSION,
        "state": state,
        "component_ids": {
            name: projection.get("source_id")
            for name, projection in components.items()
        },
        "created_at_utc": created,
    }

    report: dict[str, Any] = {
        "session_review_id": stable_id(
            "session_review",
            seed,
            24,
        ),
        "session_review_version": (
            SESSION_REVIEW_VERSION
        ),
        "status": status,
        "session_review_state": state,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "disabled_session_review_only": True,
        "actual_exchange_reconciliation_performed": False,
        "actual_session_close_authority": False,
        "future_executor_approval_required_before_any_order": True,
        "disabled_reconciliation_session_close_ready": (
            phase7_4_ready
        ),
        "reconciliation_session_close_review_packet_ready": (
            phase7_5_ready
        ),
        "disabled_session_operator_handoff_ready": (
            phase7_6_ready
        ),
        "zero_effect_evidence": zero_effect_evidence,
        "observed_fill_count": observed_fill_count,
        "observed_position_delta": observed_position_delta,
        "observed_balance_delta": observed_balance_delta,
        "source_reconciliation_mismatch_detected": (
            source_mismatch_detected
        ),
        "source_exchange_endpoint_call_detected": (
            source_endpoint_call_detected
        ),
        "source_external_order_submission_detected": (
            source_external_submission_detected
        ),
        "source_actual_order_submission_detected": (
            source_actual_submission_detected
        ),
        "source_actual_cancel_detected": (
            source_actual_cancel_detected
        ),
        "components": components,
        "blockers": blockers,
        "next_action": next_action,
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
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": (
            source_actual_submission_detected
        ),
        "actual_cancel_performed": (
            source_actual_cancel_detected
        ),
        "external_order_submission_performed": (
            source_external_submission_detected
        ),
        "exchange_endpoint_called": (
            source_endpoint_call_detected
        ),
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
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
        "created_at_utc": created,
    }

    report["session_review_sha256"] = (
        sha256_json(report)
    )

    return report


def run_session_review_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    run_executor_review_first: bool = True,
    executor_review_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    reconciliation_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    review_packet_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    handoff_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
) -> dict[str, Any]:
    """Run Phase 7.4-7.6 behind one review-only semantic entry point."""

    cfg = cfg or load_config(project_root)

    if run_executor_review_first:
        if executor_review_runner is None:
            from crypto_ai_system.governance.executor_review import (
                run_executor_review_chain,
            )

            executor_review_runner = (
                run_executor_review_chain
            )

        executor_review_runner(cfg=cfg)

    if reconciliation_runner is None:
        from crypto_ai_system.governance.phase7_steps.disabled_session_reconciliation import (
            persist_phase7_4_disabled_execution_reconciliation_session_close_report,
        )

        reconciliation_runner = (
            persist_phase7_4_disabled_execution_reconciliation_session_close_report
        )

    if review_packet_runner is None:
        from crypto_ai_system.governance.phase7_steps.session_close_review import (
            persist_phase7_5_reconciliation_session_close_review_packet_report,
        )

        review_packet_runner = (
            persist_phase7_5_reconciliation_session_close_review_packet_report
        )

    if handoff_runner is None:
        from crypto_ai_system.governance.phase7_steps.session_operator_handoff import (
            persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report,
        )

        handoff_runner = (
            persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report
        )

    reconciliation = dict(
        reconciliation_runner(
            cfg=cfg,
            run_phase7_3_first=False,
        )
    )

    review_packet = dict(
        review_packet_runner(
            cfg=cfg,
            run_phase7_4_first=False,
        )
    )

    handoff = dict(
        handoff_runner(
            cfg=cfg,
            run_phase7_5_first=False,
        )
    )

    legacy_outputs = {
        "disabled_reconciliation_session_close": (
            reconciliation
        ),
        "reconciliation_session_close_review_packet": (
            review_packet
        ),
        "disabled_session_operator_handoff": (
            handoff
        ),
    }

    report = build_session_review_report(
        legacy_outputs=legacy_outputs,
    )

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg)

    atomic_write_json(
        latest / "session_review_report.json",
        report,
    )

    atomic_write_json(
        storage / "session_review_report.json",
        report,
    )

    return {
        "report": report,
        "legacy_outputs": legacy_outputs,
    }


def run_session_review_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return run_session_review_chain(
        cfg=cfg,
        project_root=project_root,
    )["report"]


__all__ = [
    "SESSION_REVIEW_VERSION",
    "STATE_DISABLED_SESSION_REVIEW_ONLY",
    "STATE_SESSION_EVIDENCE_REPAIR_REQUIRED",
    "STATE_BLOCKED",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_REPAIR_REQUIRED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_session_review_report",
    "run_session_review_chain",
    "run_session_review_latest",
]
