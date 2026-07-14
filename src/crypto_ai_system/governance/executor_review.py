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

EXECUTOR_REVIEW_VERSION = "lean_executor_review_v1"

STATE_DISABLED_EXECUTOR_REVIEW_ONLY = (
    "DISABLED_EXECUTOR_REVIEW_ONLY"
)
STATE_REVIEW_CHAIN_REPAIR_REQUIRED = (
    "REVIEW_CHAIN_REPAIR_REQUIRED"
)
STATE_BLOCKED = "BLOCKED"

STATUS_RECORDED_REVIEW_ONLY = (
    "EXECUTOR_REVIEW_DISABLED_EVIDENCE_RECORDED_REVIEW_ONLY"
)
STATUS_REPAIR_REQUIRED_REVIEW_ONLY = (
    "EXECUTOR_REVIEW_CHAIN_REPAIR_REQUIRED_REVIEW_ONLY"
)
STATUS_BLOCKED_REVIEW_ONLY = (
    "EXECUTOR_REVIEW_BLOCKED_REVIEW_ONLY"
)

_UNSAFE_FIELDS: tuple[str, ...] = (
    "runtime_permission_source",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_executor_enablement_authority",
    "signed_testnet_order_submission_authority",
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
        "validation_design",
        "phase7_signed_testnet_validation_design_guard_id",
        "phase7_report_sha256",
    ),
    (
        "pre_submit_payload_guard",
        "phase7_1_signed_testnet_pre_submit_payload_guard_id",
        "phase7_1_report_sha256",
    ),
    (
        "review_chain_doctor",
        "phase7_1_1_review_chain_state_doctor_id",
        "phase7_1_1_report_sha256",
    ),
    (
        "enablement_review_packet",
        "phase7_2_executor_enablement_review_packet_id",
        "phase7_2_report_sha256",
    ),
    (
        "disabled_executor_review",
        "phase7_3_disabled_signed_testnet_executor_review_id",
        "phase7_3_report_sha256",
    ),
)




def _storage_dir(
    cfg: AppConfig,
) -> Path:
    return _common_storage_dir(
        cfg,
        "storage/governance/executor_review",
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


def _base_component_blockers(
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
                f"EXECUTOR_REVIEW_COMPONENT_MISSING:{name}"
            )
            continue

        if not projection.get("source_id"):
            blockers.append(
                f"EXECUTOR_REVIEW_COMPONENT_ID_MISSING:{name}"
            )

        if not projection.get("status"):
            blockers.append(
                f"EXECUTOR_REVIEW_COMPONENT_STATUS_MISSING:{name}"
            )

        if projection.get("unsafe_true_flags"):
            blockers.append(
                f"EXECUTOR_REVIEW_COMPONENT_UNSAFE_FLAG:{name}"
            )

    return blockers


def build_executor_review_report(
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

    blockers = _base_component_blockers(
        legacy_outputs=legacy_outputs,
        components=components,
    )

    design = dict(
        legacy_outputs.get("validation_design")
        or {}
    )

    payload_guard = dict(
        legacy_outputs.get("pre_submit_payload_guard")
        or {}
    )

    doctor = dict(
        legacy_outputs.get("review_chain_doctor")
        or {}
    )

    enablement = dict(
        legacy_outputs.get("enablement_review_packet")
        or {}
    )

    disabled = dict(
        legacy_outputs.get("disabled_executor_review")
        or {}
    )

    doctor_ready = (
        doctor.get("status")
        == (
            "PHASE7_1_1_REVIEW_CHAIN_STATE_DOCTOR_"
            "RECORDED_REVIEW_ONLY"
        )
        and doctor.get(
            "phase7_1_chain_ready_review_only"
        )
        is True
        and doctor.get("blocked") is False
    )

    design_ready = (
        design.get("status")
        == (
            "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_"
            "RECORDED_REVIEW_ONLY"
        )
        and design.get(
            "phase7_design_ready_review_only"
        )
        is True
        and design.get("blocked") is False
    )

    payload_guard_ready = (
        payload_guard.get("status")
        == (
            "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_"
            "GUARD_RECORDED_REVIEW_ONLY"
        )
        and payload_guard.get(
            "phase7_1_payload_guard_ready_review_only"
        )
        is True
        and payload_guard.get(
            "valid_would_submit_payload_"
            "passed_review_only_validation"
        )
        is True
        and payload_guard.get(
            "invalid_payload_fixtures_"
            "blocked_fail_closed"
        )
        is True
        and payload_guard.get(
            "disabled_executor_guard_passed"
        )
        is True
        and payload_guard.get("blocked") is False
    )

    enablement_review_ready = (
        enablement.get("status")
        == (
            "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_PACKET_"
            "RECORDED_REVIEW_ONLY"
        )
        and enablement.get(
            "phase7_2_executor_enablement_review_ready"
        )
        is True
        and enablement.get(
            "actual_executor_enablement_performed"
        )
        is False
        and enablement.get("blocked") is False
    )

    try:
        observed_endpoint_call_count = int(
            disabled.get("endpoint_call_count")
            or 0
        )
    except (TypeError, ValueError, OverflowError):
        observed_endpoint_call_count = -1

    observed_exchange_endpoint_called = (
        disabled.get("exchange_endpoint_called")
        is True
    )

    disabled_executor_ready = (
        disabled.get("status")
        == (
            "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_"
            "REVIEW_RECORDED_REVIEW_ONLY"
        )
        and disabled.get(
            "phase7_3_disabled_executor_review_ready"
        )
        is True
        and disabled.get(
            "submit_order_blocked_review_only"
        )
        is True
        and disabled.get(
            "cancel_order_blocked_review_only"
        )
        is True
        and disabled.get(
            "invalid_payload_fixtures_"
            "blocked_fail_closed"
        )
        is True
        and observed_exchange_endpoint_called is False
        and observed_endpoint_call_count == 0
        and disabled.get(
            "actual_executor_enablement_performed"
        )
        is False
        and disabled.get(
            "actual_order_submission_performed"
        )
        is False
        and disabled.get(
            "actual_cancel_performed"
        )
        is False
        and disabled.get("blocked") is False
    )

    if not doctor_ready:
        blockers.append(
            "EXECUTOR_REVIEW_CHAIN_DOCTOR_NOT_READY"
        )

    if not design_ready:
        blockers.append(
            "EXECUTOR_VALIDATION_DESIGN_NOT_READY"
        )

    if not payload_guard_ready:
        blockers.append(
            "EXECUTOR_PRE_SUBMIT_PAYLOAD_GUARD_NOT_READY"
        )

    if not enablement_review_ready:
        blockers.append(
            "EXECUTOR_ENABLEMENT_REVIEW_PACKET_NOT_READY"
        )

    if not disabled_executor_ready:
        blockers.append(
            "DISABLED_EXECUTOR_EVIDENCE_NOT_READY"
        )

    if (
        observed_exchange_endpoint_called
        or observed_endpoint_call_count != 0
    ):
        blockers.append(
            "DISABLED_EXECUTOR_ENDPOINT_CALL_EVIDENCE_INVALID"
        )

    blockers = sorted(set(blockers))

    unsafe_blocker = any(
        "UNSAFE_FLAG" in blocker
        for blocker in blockers
    )

    endpoint_blocker = (
        "DISABLED_EXECUTOR_ENDPOINT_CALL_EVIDENCE_INVALID"
        in blockers
    )

    if not blockers:
        state = (
            STATE_DISABLED_EXECUTOR_REVIEW_ONLY
        )

        status = STATUS_RECORDED_REVIEW_ONLY

        next_action = (
            "prepare_phase7_session_review_only_"
            "keep_executor_disabled"
        )
    elif (
        not doctor_ready
        and not unsafe_blocker
        and not endpoint_blocker
    ):
        state = (
            STATE_REVIEW_CHAIN_REPAIR_REQUIRED
        )

        status = (
            STATUS_REPAIR_REQUIRED_REVIEW_ONLY
        )

        next_action = (
            "inspect_review_chain_doctor_"
            "and_repair_first_blocked_step"
        )
    else:
        state = STATE_BLOCKED

        status = STATUS_BLOCKED_REVIEW_ONLY

        next_action = (
            "resolve_executor_review_"
            "structural_or_safety_blockers"
        )

    doctor_summary = (
        doctor.get("doctor_summary")
        if isinstance(
            doctor.get("doctor_summary"),
            Mapping,
        )
        else {}
    )

    fixture_sync_detected = (
        doctor_summary.get(
            "review_only_actual_fixtures_synced"
        )
        is True
    )

    seed = {
        "version": EXECUTOR_REVIEW_VERSION,
        "state": state,
        "component_ids": {
            name: projection.get("source_id")
            for name, projection in components.items()
        },
        "created_at_utc": created,
    }

    report: dict[str, Any] = {
        "executor_review_id": stable_id(
            "executor_review",
            seed,
            24,
        ),
        "executor_review_version": (
            EXECUTOR_REVIEW_VERSION
        ),
        "status": status,
        "executor_review_state": state,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "design_only": True,
        "disabled_executor_review_only": True,
        "manual_approval_required": True,
        "separate_future_executor_approval_required": True,
        "review_only_fixture_sync_detected": (
            fixture_sync_detected
        ),
        "review_only_fixture_sync_is_runtime_approval": False,
        "runtime_approval_created_by_doctor": False,
        "review_chain_ready": doctor_ready,
        "validation_design_ready": design_ready,
        "pre_submit_payload_guard_ready": (
            payload_guard_ready
        ),
        "enablement_review_packet_ready": (
            enablement_review_ready
        ),
        "disabled_executor_evidence_ready": (
            disabled_executor_ready
        ),
        "submit_order_blocked_review_only": (
            disabled.get(
                "submit_order_blocked_review_only"
            )
            is True
        ),
        "cancel_order_blocked_review_only": (
            disabled.get(
                "cancel_order_blocked_review_only"
            )
            is True
        ),
        "exchange_endpoint_called": (
            observed_exchange_endpoint_called
        ),
        "endpoint_call_count": (
            observed_endpoint_call_count
        ),
        "components": components,
        "blockers": blockers,
        "next_action": next_action,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_enablement_authority": False,
        "signed_testnet_order_submission_authority": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
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
        "external_order_submission_performed": False,
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

    report["executor_review_sha256"] = (
        sha256_json(report)
    )

    return report


def run_executor_review_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    design_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    payload_guard_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    doctor_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    enablement_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    disabled_executor_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
) -> dict[str, Any]:
    """Run Phase 7-M1 behind one review-only semantic entry point."""

    cfg = cfg or load_config(project_root)

    if design_runner is None:
        from crypto_ai_system.governance.phase7_steps.validation_design import (
            persist_phase7_signed_testnet_validation_design_guard_report,
        )

        design_runner = (
            persist_phase7_signed_testnet_validation_design_guard_report
        )

    if payload_guard_runner is None:
        from crypto_ai_system.governance.phase7_steps.pre_submit_guard import (
            persist_phase7_1_signed_testnet_pre_submit_payload_guard_report,
        )

        payload_guard_runner = (
            persist_phase7_1_signed_testnet_pre_submit_payload_guard_report
        )

    if doctor_runner is None:
        from crypto_ai_system.governance.phase7_steps.review_chain_doctor import (
            persist_phase7_1_review_chain_state_doctor_report,
        )

        doctor_runner = (
            persist_phase7_1_review_chain_state_doctor_report
        )

    if enablement_runner is None:
        from crypto_ai_system.governance.phase7_steps.executor_enablement_review import (
            persist_phase7_2_executor_enablement_review_packet_report,
        )

        enablement_runner = (
            persist_phase7_2_executor_enablement_review_packet_report
        )

    if disabled_executor_runner is None:
        from crypto_ai_system.governance.phase7_steps.disabled_executor_review import (
            persist_phase7_3_disabled_signed_testnet_executor_review_report,
        )

        disabled_executor_runner = (
            persist_phase7_3_disabled_signed_testnet_executor_review_report
        )

    # The doctor intentionally rebuilds the upstream review-only chain.
    # Running it once here avoids the historical repeated doctor execution
    # inside Phase 7.2 and 7.3.
    doctor = dict(
        doctor_runner(
            cfg=cfg,
            sync_review_only_actual_fixtures=True,
        )
    )

    design = dict(
        design_runner(cfg=cfg)
    )

    payload_guard = dict(
        payload_guard_runner(cfg=cfg)
    )

    enablement = dict(
        enablement_runner(
            cfg=cfg,
            run_review_chain_first=False,
        )
    )

    disabled_executor = dict(
        disabled_executor_runner(
            cfg=cfg,
            run_phase7_2_first=False,
        )
    )

    legacy_outputs = {
        "validation_design": design,
        "pre_submit_payload_guard": payload_guard,
        "review_chain_doctor": doctor,
        "enablement_review_packet": enablement,
        "disabled_executor_review": disabled_executor,
    }

    report = build_executor_review_report(
        legacy_outputs=legacy_outputs,
    )

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg)

    atomic_write_json(
        latest / "executor_review_report.json",
        report,
    )

    atomic_write_json(
        storage / "executor_review_report.json",
        report,
    )

    return {
        "report": report,
        "legacy_outputs": legacy_outputs,
    }


def run_executor_review_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return run_executor_review_chain(
        cfg=cfg,
        project_root=project_root,
    )["report"]


__all__ = [
    "EXECUTOR_REVIEW_VERSION",
    "STATE_DISABLED_EXECUTOR_REVIEW_ONLY",
    "STATE_REVIEW_CHAIN_REPAIR_REQUIRED",
    "STATE_BLOCKED",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_REPAIR_REQUIRED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_executor_review_report",
    "run_executor_review_chain",
    "run_executor_review_latest",
]
