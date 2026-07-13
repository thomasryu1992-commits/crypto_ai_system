from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.readiness_common import (
    preparation_artifact_summary as _artifact_summary,
    latest_dir as _latest_dir,
    read_latest_json as _read_latest_json,
    bool_value as _safe_bool,
    storage_dir as _storage_dir,
    unsafe_flags_by_artifact as _unsafe_flags_by_artifact,
)
from crypto_ai_system.execution.real_read_only_venue_probe import run_real_read_only_venue_probe_latest
from crypto_ai_system.execution.real_testnet_read_only_adapter import run_real_testnet_read_only_adapter_latest
from crypto_ai_system.execution.signed_testnet_execution_enablement_packet import run_signed_testnet_execution_enablement_packet_latest
from crypto_ai_system.execution.signed_testnet_order_executor import run_signed_testnet_order_executor_latest
from crypto_ai_system.execution.signed_testnet_pre_submit_validator import run_signed_testnet_pre_submit_validator_latest
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import run_testnet_secret_metadata_intake_latest
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE6_VERSION = "phase6_signed_testnet_preparation_preview_v1"
PHASE6_REGISTRY_NAME = "phase6_signed_testnet_preparation_preview_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_BLOCKED_REVIEW_ONLY"

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
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
    "auto_promotion_allowed",
]


def build_phase6_signed_testnet_preparation_preview_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    real_testnet_read_only_adapter: Mapping[str, Any] | None = None,
    testnet_secret_metadata_intake: Mapping[str, Any] | None = None,
    real_read_only_venue_probe: Mapping[str, Any] | None = None,
    signed_testnet_pre_submit_validation: Mapping[str, Any] | None = None,
    signed_testnet_execution_enablement_packet: Mapping[str, Any] | None = None,
    signed_testnet_order_execution_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    phase5_2 = _read_latest_json(cfg, "phase5_2_manual_approval_submission_fixture_validator_report.json")
    phase5 = _read_latest_json(cfg, "phase5_manual_approval_intake_validation_report.json")
    actual_submission_path = cfg.root / "storage" / "manual_approval" / "approval_intake_submission.json"

    adapter = dict(real_testnet_read_only_adapter or _read_latest_json(cfg, "real_testnet_read_only_adapter_evidence.json"))
    secret = dict(testnet_secret_metadata_intake or _read_latest_json(cfg, "testnet_secret_metadata_intake_v2.json"))
    probe = dict(real_read_only_venue_probe or _read_latest_json(cfg, "real_read_only_venue_probe.json"))
    pre_submit = dict(signed_testnet_pre_submit_validation or _read_latest_json(cfg, "signed_testnet_pre_submit_validation_report.json"))
    enablement = dict(signed_testnet_execution_enablement_packet or _read_latest_json(cfg, "signed_testnet_execution_enablement_packet.json"))
    executor = dict(signed_testnet_order_execution_record or _read_latest_json(cfg, "signed_testnet_order_execution_record.json"))

    artifacts: dict[str, Mapping[str, Any]] = {
        "real_testnet_read_only_adapter": adapter,
        "testnet_secret_metadata_intake": secret,
        "real_read_only_venue_probe": probe,
        "signed_testnet_pre_submit_validation": pre_submit,
        "signed_testnet_execution_enablement_packet": enablement,
        "signed_testnet_order_execution_record": executor,
    }
    missing_artifacts = [name for name, payload in artifacts.items() if not payload]
    unsafe_flags = _unsafe_flags_by_artifact(artifacts)

    readiness_blockers: list[str] = []
    if phase5_2.get("status") != "PHASE5_2_MANUAL_APPROVAL_SUBMISSION_FIXTURE_VALIDATOR_RECORDED_REVIEW_ONLY":
        readiness_blockers.append("PHASE5_2_FIXTURE_VALIDATOR_NOT_READY")
    if actual_submission_path.exists():
        readiness_blockers.append("ACTUAL_MANUAL_APPROVAL_SUBMISSION_PRESENT_UNEXPECTED")
    else:
        readiness_blockers.append("ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING")
    if phase5.get("approval_intake_validated") is not False:
        readiness_blockers.append("APPROVAL_INTAKE_VALIDATED_UNEXPECTED")
    else:
        readiness_blockers.append("APPROVAL_INTAKE_NOT_VALIDATED")
    if not _read_latest_json(cfg, "operator_unlock_request.json"):
        readiness_blockers.append("OPERATOR_UNLOCK_REQUEST_MISSING")
    if phase5.get("status") != "PHASE5_MANUAL_APPROVAL_INTAKE_BLOCKED_REVIEW_ONLY":
        readiness_blockers.append("PHASE5_INTAKE_NOT_BLOCKED_BASELINE")
    if missing_artifacts:
        readiness_blockers.extend([f"MISSING_PHASE6_ARTIFACT:{name}" for name in missing_artifacts])
    if unsafe_flags:
        readiness_blockers.extend([f"UNSAFE_PHASE6_FLAG:{name}:{','.join(flags)}" for name, flags in unsafe_flags.items()])

    blocker_set = sorted(dict.fromkeys(readiness_blockers))
    unsafe = bool(unsafe_flags)
    blocked = unsafe or bool(missing_artifacts)
    # Missing actual approval keeps signed testnet disabled, but does not block recording a preparation preview.
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    preview_id = stable_id(
        "phase6_signed_testnet_preparation_preview",
        {
            "phase5_2_id": phase5_2.get("phase5_2_manual_approval_submission_fixture_validator_id"),
            "pre_submit_status": pre_submit.get("status"),
            "enablement_status": enablement.get("status"),
            "executor_status": executor.get("status"),
            "created_at_utc": created,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase6_signed_testnet_preparation_preview_id": preview_id,
        "phase6_version": PHASE6_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": bool(blocked),
        "review_only": True,
        "signed_testnet_preparation_preview_only": True,
        "actual_manual_approval_submission_present": actual_submission_path.exists(),
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "operator_unlock_request_present": bool(_read_latest_json(cfg, "operator_unlock_request.json")),
        "read_only_venue_probe_recorded": bool(probe),
        "metadata_only_key_reference_recorded": bool(secret),
        "pre_submit_validation_recorded": bool(pre_submit),
        "disabled_executor_evidence_recorded": bool(executor),
        "enablement_packet_recorded": bool(enablement),
        "signed_testnet_preparation_ready": False,
        "signed_testnet_preparation_ready_reason": "manual_approval_intake_not_validated_and_execution_flags_disabled",
        "readiness_blockers": blocker_set,
        "missing_phase6_artifacts": missing_artifacts,
        "unsafe_flags_by_artifact": unsafe_flags,
        "artifact_summaries": {
            name: _artifact_summary(name, payload)
            for name, payload in artifacts.items()
        },
        "phase5_status": phase5.get("status"),
        "phase5_2_status": phase5_2.get("status"),
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
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "recommended_next_action": "create_real_manual_approval_submission_only_after_human_review_then_rerun_phase5_intake_validation",
        "created_at_utc": created,
    }
    report["phase6_report_sha256"] = sha256_json(report)
    return report


def persist_phase6_signed_testnet_preparation_preview_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    # Build fresh read-only/preparation artifacts. These functions are review-safe and keep execution disabled.
    adapter = run_real_testnet_read_only_adapter_latest(project_root=cfg.root)
    secret = run_testnet_secret_metadata_intake_latest(project_root=cfg.root)
    probe = run_real_read_only_venue_probe_latest(project_root=cfg.root, secret_metadata=secret)
    pre_submit = run_signed_testnet_pre_submit_validator_latest(project_root=cfg.root, venue_probe=probe)
    enablement = run_signed_testnet_execution_enablement_packet_latest(
        project_root=cfg.root,
        operator_unlock_request={},
        pre_submit_validation_report=pre_submit,
        venue_probe=probe,
    )
    executor = run_signed_testnet_order_executor_latest(
        project_root=cfg.root,
        enablement_packet=enablement,
    )

    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase6_signed_testnet_preparation_preview")
    report = build_phase6_signed_testnet_preparation_preview_report(
        cfg=cfg,
        real_testnet_read_only_adapter=adapter,
        testnet_secret_metadata_intake=secret,
        real_read_only_venue_probe=probe,
        signed_testnet_pre_submit_validation=pre_submit,
        signed_testnet_execution_enablement_packet=enablement,
        signed_testnet_order_execution_record=executor,
    )
    atomic_write_json(latest / "phase6_signed_testnet_preparation_preview_report.json", report)
    atomic_write_json(phase_dir / "phase6_signed_testnet_preparation_preview_report.json", report)

    registry_record = append_registry_record(
        registry_path(cfg, PHASE6_REGISTRY_NAME),
        {
            "phase6_signed_testnet_preparation_preview_id": report.get("phase6_signed_testnet_preparation_preview_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "signed_testnet_preparation_ready": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "api_key_value_access_allowed": False,
            "secret_file_access_allowed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE6_REGISTRY_NAME,
        id_field="phase6_signed_testnet_preparation_preview_registry_record_id",
        hash_field="phase6_signed_testnet_preparation_preview_registry_record_sha256",
        id_prefix="phase6_signed_testnet_preparation_preview_registry_record",
    )
    atomic_write_json(latest / "phase6_signed_testnet_preparation_preview_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase6_signed_testnet_preparation_preview_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE6_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase6_signed_testnet_preparation_preview_report",
    "persist_phase6_signed_testnet_preparation_preview_report",
]
