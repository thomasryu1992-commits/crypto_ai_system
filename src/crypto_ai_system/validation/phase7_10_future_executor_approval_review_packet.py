from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_9_future_executor_approval_intake_validator import (
    persist_phase7_9_future_executor_approval_intake_validator_report,
)

PHASE7_10_VERSION = "phase7_10_future_executor_approval_review_packet_v1"
PHASE7_10_REGISTRY_NAME = "phase7_10_future_executor_approval_review_packet_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_9_intake_validator": "phase7_9_future_executor_approval_intake_validator_report.json",
    "future_executor_approval_intake_validation_record": "future_signed_testnet_executor_approval_intake_validation_record_review_only.json",
    "future_executor_approval_intake_guard": "future_signed_testnet_executor_approval_intake_guard_report.json",
    "future_executor_approval_template": "future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json",
    "future_executor_prerequisite_packet": "future_signed_testnet_executor_review_prerequisite_packet_review_only.json",
}

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
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
]


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(fields)


def _unsafe_flags_by_artifact(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    unsafe: dict[str, list[str]] = {}
    for name, payload in artifacts.items():
        flags = _unsafe_fields(payload)
        if flags:
            unsafe[name] = flags
    return unsafe


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase7_10_report_sha256",
        "phase7_9_report_sha256",
        "future_executor_approval_intake_validation_record_sha256",
        "future_executor_approval_intake_guard_report_sha256",
        "future_executor_approval_template_sha256",
        "future_executor_prerequisite_packet_sha256",
        "future_executor_approval_review_packet_sha256",
        "future_executor_approval_review_guard_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("record_type") or data.get("guard_type") or data.get("template_type") or data.get("packet_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _build_review_packet(*, report_id: str, artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase7_9 = artifacts.get("phase7_9_intake_validator", {})
    validation_record = artifacts.get("future_executor_approval_intake_validation_record", {})
    intake_guard = artifacts.get("future_executor_approval_intake_guard", {})
    template = artifacts.get("future_executor_approval_template", {})
    prerequisite_packet = artifacts.get("future_executor_prerequisite_packet", {})
    source_hash_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    validation = validation_record.get("validation") or phase7_9.get("validation") or {}
    return {
        "packet_type": "future_signed_testnet_executor_approval_review_packet_review_only",
        "phase7_10_version": PHASE7_10_VERSION,
        "source_phase7_10_report_id": report_id,
        "source_phase7_9_report_id": phase7_9.get("phase7_9_future_executor_approval_intake_validator_id"),
        "review_only": True,
        "approval_review_packet_only": True,
        "not_runtime_authority": True,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "future_executor_approval_intake_validated_review_only": validation_record.get("submission_valid_review_only") is True,
        "future_executor_approval_intake_guard_passed": intake_guard.get("guard_passed") is True,
        "metadata_only_key_reference_validated_review_only": validation.get("metadata_only_key_reference_present") is True
        and validation.get("metadata_only_key_fingerprint_present") is True,
        "prerequisite_packet_hash_matches": validation.get("prerequisite_packet_hash_matches") is True,
        "hard_caps_numeric": validation.get("hard_caps_numeric") is True,
        "fresh_rechecks_true": validation.get("fresh_rechecks_true") is True,
        "template_hash": sha256_json(dict(template or {})) if template else None,
        "prerequisite_packet_hash": sha256_json(dict(prerequisite_packet or {})) if prerequisite_packet else None,
        "intake_validation_record_hash": sha256_json(dict(validation_record or {})) if validation_record else None,
        "intake_guard_hash": sha256_json(dict(intake_guard or {})) if intake_guard else None,
        "operator_review_checklist": [
            "Confirm Phase 7.9 intake validation is recorded review-only and not runtime authority.",
            "Confirm metadata-only key reference and fingerprint are present; no key values are stored.",
            "Confirm hard caps remain within review limits before any later executor review.",
            "Confirm fresh pre-submit payload validation is required before any later executor review.",
            "Confirm fresh PreOrderRiskGate recheck is required before any later executor review.",
            "Confirm manual kill switch confirmation is required before any later executor review.",
            "Confirm reconciliation and session close evidence remain mandatory after any future session.",
            "Confirm place_order, cancel_order, and signed_order_executor flags remain false.",
        ],
        "allowed_next_scope": "future_executor_enablement_design_review_still_disabled",
        "forbidden_scope": [
            "actual_signed_testnet_order_submission",
            "actual_executor_approval_authority",
            "actual_executor_enablement",
            "place_order_enablement",
            "cancel_order_enablement",
            "signed_executor_enablement",
            "api_key_value_access",
            "api_secret_value_access",
            "secret_file_read_or_creation",
            "settings_yaml_mutation",
            "runtime_score_weights_mutation",
            "automatic_promotion_to_signed_testnet_or_live",
        ],
        "source_evidence_hash_summary": source_hash_summary,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_review_guard(*, report_id: str, packet: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    source_flags = _unsafe_flags_by_artifact(artifacts)
    packet_flags = _unsafe_fields(packet)
    all_flags = dict(source_flags)
    if packet_flags:
        all_flags["future_executor_approval_review_packet"] = packet_flags
    missing_review_prereqs: list[str] = []
    if packet.get("future_executor_approval_intake_validated_review_only") is not True:
        missing_review_prereqs.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_NOT_VALIDATED_REVIEW_ONLY")
    if packet.get("future_executor_approval_intake_guard_passed") is not True:
        missing_review_prereqs.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_GUARD_NOT_PASSED")
    if packet.get("metadata_only_key_reference_validated_review_only") is not True:
        missing_review_prereqs.append("METADATA_ONLY_KEY_REFERENCE_NOT_VALIDATED_REVIEW_ONLY")
    if packet.get("prerequisite_packet_hash_matches") is not True:
        missing_review_prereqs.append("PREREQUISITE_PACKET_HASH_NOT_MATCHED")
    if packet.get("hard_caps_numeric") is not True:
        missing_review_prereqs.append("HARD_CAPS_NOT_NUMERIC")
    if packet.get("fresh_rechecks_true") is not True:
        missing_review_prereqs.append("FRESH_RECHECKS_NOT_TRUE")
    guard_passed = not all_flags and not missing_review_prereqs and packet.get("review_only") is True
    return {
        "guard_type": "future_signed_testnet_executor_approval_review_guard_review_only",
        "phase7_10_version": PHASE7_10_VERSION,
        "source_phase7_10_report_id": report_id,
        "review_only": True,
        "approval_review_guard_only": True,
        "guard_passed": guard_passed,
        "missing_review_prerequisites": missing_review_prereqs,
        "unsafe_flags_by_artifact": all_flags,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 7.10 Future Executor Approval Review Packet — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase packages Phase 7.9 future executor approval intake validation into an operator review packet. It does not create runtime executor approval, enable execution, submit orders, read secrets, mutate settings, or promote to testnet/live.",
            "",
            "## Result",
            "",
            f"- Review packet ready: `{report.get('phase7_10_review_packet_ready')}`",
            f"- Review packet created: `{report.get('future_executor_approval_review_packet_created')}`",
            f"- Review guard passed: `{report.get('review_guard_passed')}`",
            "",
            "## Safety Flags",
            "",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `external_order_submission_performed=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase7_10_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_10_future_executor_approval_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_9_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_9_first:
        persist_phase7_9_future_executor_approval_intake_validator_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    phase7_9 = artifacts.get("phase7_9_intake_validator", {})
    validation_record = artifacts.get("future_executor_approval_intake_validation_record", {})
    intake_guard = artifacts.get("future_executor_approval_intake_guard", {})

    preliminary_id = stable_id("phase7_10_future_executor_approval_review_packet", {"source_summary": source_summary, "created_at_utc": created}, 24)
    packet = _build_review_packet(report_id=preliminary_id, artifacts=artifacts, created_at_utc=created)
    guard = _build_review_guard(report_id=preliminary_id, packet=packet, artifacts=artifacts, created_at_utc=created)

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_10_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_10_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_9.get("status") != "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATOR_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_9_INTAKE_VALIDATOR_NOT_READY")
    if phase7_9.get("phase7_9_intake_validation_ready") is not True:
        blockers.append("PHASE7_9_INTAKE_VALIDATION_NOT_READY")
    if validation_record.get("record_type") != "future_signed_testnet_executor_approval_intake_validation_record_review_only":
        blockers.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATION_RECORD_INVALID")
    if validation_record.get("submission_valid_review_only") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATION_RECORD_NOT_VALID")
    if intake_guard.get("guard_type") != "future_signed_testnet_executor_approval_intake_guard_review_only":
        blockers.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_GUARD_INVALID")
    if intake_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_GUARD_NOT_PASSED")
    if guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_REVIEW_GUARD_NOT_PASSED")
        blockers.extend(guard.get("missing_review_prerequisites") or [])

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_10_future_executor_approval_review_packet",
        {
            "source_summary": source_summary,
            "packet_hash": sha256_json(packet),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    packet = {**packet, "source_phase7_10_report_id": report_id}
    guard = {**guard, "source_phase7_10_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_10_future_executor_approval_review_packet_id": report_id,
        "phase7_10_version": PHASE7_10_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "approval_review_packet_only": True,
        "phase7_10_review_packet_ready": ready,
        "future_executor_approval_review_packet_created": True,
        "future_executor_approval_review_guard_created": True,
        "review_guard_passed": guard.get("guard_passed") is True,
        "phase7_9_intake_validation_ready": phase7_9.get("phase7_9_intake_validation_ready") is True,
        "future_executor_approval_intake_validation_record_valid": validation_record.get("submission_valid_review_only") is True,
        "future_executor_approval_intake_guard_passed": intake_guard.get("guard_passed") is True,
        "metadata_only_key_reference_validated_review_only": packet.get("metadata_only_key_reference_validated_review_only") is True,
        "prerequisite_packet_hash_matches": packet.get("prerequisite_packet_hash_matches") is True,
        "hard_caps_numeric": packet.get("hard_caps_numeric") is True,
        "fresh_rechecks_true": packet.get("fresh_rechecks_true") is True,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "future_executor_approval_review_required_before_enablement": True,
        "future_executor_enablement_review_required_before_any_order": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_10_allowed_next_scope": "future_executor_enablement_design_review_still_disabled" if ready else "resolve_phase7_10_review_packet_blockers",
        "recommended_next_action": "prepare_phase7_11_future_executor_enablement_design_keep_execution_disabled" if ready else "inspect_phase7_10_blockers_and_rerun_phase7_9_phase7_10",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
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
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    packet["future_executor_approval_review_packet_sha256"] = sha256_json(packet)
    guard["future_executor_approval_review_guard_report_sha256"] = sha256_json(guard)
    report["future_executor_approval_review_packet_sha256"] = packet["future_executor_approval_review_packet_sha256"]
    report["future_executor_approval_review_guard_report_sha256"] = guard["future_executor_approval_review_guard_report_sha256"]
    report["phase7_10_report_sha256"] = sha256_json(report)
    return report, packet, guard


def persist_phase7_10_future_executor_approval_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_9_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_10_future_executor_approval_review_packet")
    report, packet, guard = build_phase7_10_future_executor_approval_review_packet_report(cfg=cfg, run_phase7_9_first=run_phase7_9_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_10_future_executor_approval_review_packet_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_approval_review_packet_review_only.json", packet)
    atomic_write_json(latest / "future_signed_testnet_executor_approval_review_guard_report.json", guard)
    (latest / "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(phase_dir / "phase7_10_future_executor_approval_review_packet_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_approval_review_packet_review_only.json", packet)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_approval_review_guard_report.json", guard)
    (phase_dir / "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_10_REGISTRY_NAME),
        {
            "phase7_10_future_executor_approval_review_packet_id": report.get("phase7_10_future_executor_approval_review_packet_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_10_review_packet_ready": report.get("phase7_10_review_packet_ready"),
            "review_guard_passed": report.get("review_guard_passed"),
            "actual_executor_approval_created": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
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
        registry_name=PHASE7_10_REGISTRY_NAME,
        id_field="phase7_10_future_executor_approval_review_packet_registry_record_id",
        hash_field="phase7_10_future_executor_approval_review_packet_registry_record_sha256",
        id_prefix="phase7_10_future_executor_approval_review_packet_registry_record",
    )
    atomic_write_json(latest / "phase7_10_future_executor_approval_review_packet_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_10_future_executor_approval_review_packet_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_10_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_10_future_executor_approval_review_packet_report",
    "persist_phase7_10_future_executor_approval_review_packet_report",
]
