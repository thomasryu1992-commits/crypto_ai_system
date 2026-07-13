from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.readiness_common import (
    artifact_hash as _artifact_hash,
    source_summary as _artifact_summary,
    latest_dir as _latest_dir,
    read_latest_json as _read_latest_json,
    bool_value as _safe_bool,
    storage_dir as _storage_dir,
    unsafe_flags_by_artifact as _unsafe_flags_by_artifact,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE6_3_VERSION = "phase6_3_signed_testnet_readiness_gate_review_v1"
PHASE6_3_REGISTRY_NAME = "phase6_3_signed_testnet_readiness_gate_review_registry"

STATUS_BLOCKED_REVIEW_ONLY = "PHASE6_3_SIGNED_TESTNET_READINESS_GATE_BLOCKED_REVIEW_ONLY"
STATUS_RECORDED_REVIEW_ONLY = "PHASE6_3_SIGNED_TESTNET_READINESS_GATE_RECORDED_REVIEW_ONLY"

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
    "live_trading_allowed",
    "auto_promotion_allowed",
]

REQUIRED_SOURCE_ARTIFACTS = {
    "phase5_manual_approval_intake_validation": "phase5_manual_approval_intake_validation_report.json",
    "phase5_2_manual_approval_submission_fixture_validator": "phase5_2_manual_approval_submission_fixture_validator_report.json",
    "phase6_signed_testnet_preparation_preview": "phase6_signed_testnet_preparation_preview_report.json",
    "phase6_1_operator_unlock_request_template": "phase6_1_signed_testnet_operator_unlock_request_template_report.json",
    "phase6_2_operator_unlock_request_fixture_validator": "phase6_2_operator_unlock_request_fixture_validator_report.json",
}


def build_phase6_3_signed_testnet_readiness_gate_review_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    latest = _latest_dir(cfg)

    artifacts = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_ARTIFACTS.items()}
    phase5 = artifacts["phase5_manual_approval_intake_validation"]
    phase5_2 = artifacts["phase5_2_manual_approval_submission_fixture_validator"]
    phase6 = artifacts["phase6_signed_testnet_preparation_preview"]
    phase6_1 = artifacts["phase6_1_operator_unlock_request_template"]
    phase6_2 = artifacts["phase6_2_operator_unlock_request_fixture_validator"]

    actual_approval_path = cfg.root / "storage" / "manual_approval" / "approval_intake_submission.json"
    actual_unlock_latest_path = latest / "operator_unlock_request.json"
    actual_unlock_archive_path = cfg.root / "storage" / "signed_testnet" / "operator_unlock_request.json"
    actual_approval_present = actual_approval_path.exists()
    actual_unlock_present = actual_unlock_latest_path.exists() or actual_unlock_archive_path.exists()

    missing_artifacts = [name for name, payload in artifacts.items() if not payload]
    unsafe_flags = _unsafe_flags_by_artifact(artifacts)
    readiness_blockers: list[str] = []

    if missing_artifacts:
        readiness_blockers.extend([f"MISSING_READINESS_SOURCE_ARTIFACT:{name}" for name in missing_artifacts])
    if phase5.get("status") != "PHASE5_MANUAL_APPROVAL_INTAKE_BLOCKED_REVIEW_ONLY":
        readiness_blockers.append("PHASE5_INTAKE_BASELINE_NOT_BLOCKED_REVIEW_ONLY")
    if phase5.get("approval_intake_validated") is not False:
        readiness_blockers.append("APPROVAL_INTAKE_VALIDATED_UNEXPECTED")
    else:
        readiness_blockers.append("APPROVAL_INTAKE_NOT_VALIDATED")
    if not actual_approval_present:
        readiness_blockers.append("ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING")
    if phase5_2.get("status") != "PHASE5_2_MANUAL_APPROVAL_SUBMISSION_FIXTURE_VALIDATOR_RECORDED_REVIEW_ONLY":
        readiness_blockers.append("PHASE5_2_APPROVAL_FIXTURE_VALIDATOR_NOT_READY")
    if phase6.get("status") != "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_RECORDED_REVIEW_ONLY":
        readiness_blockers.append("PHASE6_PREPARATION_PREVIEW_NOT_RECORDED")
    if phase6.get("signed_testnet_preparation_ready") is not False:
        readiness_blockers.append("SIGNED_TESTNET_PREPARATION_READY_UNEXPECTED")
    else:
        readiness_blockers.append("SIGNED_TESTNET_PREPARATION_READY_FALSE")
    if phase6_1.get("status") != "PHASE6_1_SIGNED_TESTNET_OPERATOR_UNLOCK_REQUEST_TEMPLATE_RECORDED_REVIEW_ONLY":
        readiness_blockers.append("PHASE6_1_OPERATOR_UNLOCK_TEMPLATE_NOT_RECORDED")
    if phase6_2.get("status") != "PHASE6_2_OPERATOR_UNLOCK_REQUEST_FIXTURE_VALIDATOR_RECORDED_REVIEW_ONLY":
        readiness_blockers.append("PHASE6_2_OPERATOR_UNLOCK_FIXTURE_VALIDATOR_NOT_READY")
    if phase6_2.get("operator_unlock_request_validated") is not False:
        readiness_blockers.append("OPERATOR_UNLOCK_REQUEST_VALIDATED_UNEXPECTED")
    else:
        readiness_blockers.append("OPERATOR_UNLOCK_REQUEST_NOT_VALIDATED")
    if not actual_unlock_present:
        readiness_blockers.append("ACTUAL_OPERATOR_UNLOCK_REQUEST_MISSING")
    if unsafe_flags:
        readiness_blockers.extend([f"UNSAFE_READINESS_SOURCE_FLAG:{name}:{','.join(flags)}" for name, flags in unsafe_flags.items()])

    readiness_blockers = sorted(dict.fromkeys(readiness_blockers))
    approval_ready = actual_approval_present and phase5.get("approval_intake_validated") is True
    operator_ready = actual_unlock_present and phase6_2.get("operator_unlock_request_validated") is True
    evidence_ready = not missing_artifacts and not unsafe_flags and phase6.get("status") == "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_RECORDED_REVIEW_ONLY"
    signed_testnet_readiness_passed = approval_ready and operator_ready and evidence_ready and phase6.get("signed_testnet_preparation_ready") is True

    # In this review-only package, the readiness gate must remain blocked until real manual approval
    # and a real operator unlock request are present and separately validated.
    blocked = True if readiness_blockers or not signed_testnet_readiness_passed else True
    phase6_3_id = stable_id(
        "phase6_3_signed_testnet_readiness_gate_review",
        {
            "phase5_hash": _artifact_hash(phase5),
            "phase6_hash": _artifact_hash(phase6),
            "phase6_2_hash": _artifact_hash(phase6_2),
            "created_at_utc": created,
            "readiness_blockers": readiness_blockers,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase6_3_signed_testnet_readiness_gate_review_id": phase6_3_id,
        "phase6_3_version": PHASE6_3_VERSION,
        "status": STATUS_BLOCKED_REVIEW_ONLY,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "signed_testnet_readiness_gate_review_only": True,
        "actual_manual_approval_submission_present": actual_approval_present,
        "actual_operator_unlock_request_present": actual_unlock_present,
        "approval_intake_validated": False,
        "operator_unlock_request_validated": False,
        "signed_testnet_preparation_ready": False,
        "signed_testnet_readiness_passed": False,
        "signed_testnet_readiness_status": "SIGNED_TESTNET_READINESS_BLOCKED_REVIEW_ONLY",
        "readiness_blockers": readiness_blockers,
        "missing_readiness_source_artifacts": missing_artifacts,
        "unsafe_flags_by_artifact": unsafe_flags,
        "source_artifact_summaries": {name: _artifact_summary(name, payload) for name, payload in artifacts.items()},
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
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "recommended_next_action": "collect_real_manual_approval_submission_and_real_operator_unlock_request_then_rerun_phase5_and_phase6_readiness_reviews",
        "created_at_utc": created,
    }
    report["phase6_3_report_sha256"] = sha256_json(report)
    return report


def persist_phase6_3_signed_testnet_readiness_gate_review_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase6_3_signed_testnet_readiness_gate_review")
    report = build_phase6_3_signed_testnet_readiness_gate_review_report(cfg=cfg)
    atomic_write_json(latest / "phase6_3_signed_testnet_readiness_gate_review_report.json", report)
    atomic_write_json(phase_dir / "phase6_3_signed_testnet_readiness_gate_review_report.json", report)
    registry_record = append_registry_record(
        registry_path(cfg, PHASE6_3_REGISTRY_NAME),
        {
            "phase6_3_signed_testnet_readiness_gate_review_id": report.get("phase6_3_signed_testnet_readiness_gate_review_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "actual_manual_approval_submission_present": report.get("actual_manual_approval_submission_present"),
            "actual_operator_unlock_request_present": report.get("actual_operator_unlock_request_present"),
            "approval_intake_validated": False,
            "operator_unlock_request_validated": False,
            "signed_testnet_readiness_passed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "external_order_submission_performed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE6_3_REGISTRY_NAME,
        id_field="phase6_3_signed_testnet_readiness_gate_review_registry_record_id",
        hash_field="phase6_3_signed_testnet_readiness_gate_review_registry_record_sha256",
        id_prefix="phase6_3_signed_testnet_readiness_gate_review_registry_record",
    )
    atomic_write_json(latest / "phase6_3_signed_testnet_readiness_gate_review_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase6_3_signed_testnet_readiness_gate_review_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE6_3_VERSION",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "STATUS_RECORDED_REVIEW_ONLY",
    "build_phase6_3_signed_testnet_readiness_gate_review_report",
    "persist_phase6_3_signed_testnet_readiness_gate_review_report",
]
