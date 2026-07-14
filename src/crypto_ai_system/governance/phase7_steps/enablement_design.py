from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.executor_approval_packet_review import (
    persist_phase7_10_future_executor_approval_review_packet_report,
)

PHASE7_11_VERSION = "phase7_11_future_executor_enablement_design_review_v1"
PHASE7_11_REGISTRY_NAME = "phase7_11_future_executor_enablement_design_review_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_DESIGN_REVIEW_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_DESIGN_REVIEW_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_10_approval_review_packet": "phase7_10_future_executor_approval_review_packet_report.json",
    "future_executor_approval_review_packet": "future_signed_testnet_executor_approval_review_packet_review_only.json",
    "future_executor_approval_review_guard": "future_signed_testnet_executor_approval_review_guard_report.json",
    "future_executor_approval_intake_validation_record": "future_signed_testnet_executor_approval_intake_validation_record_review_only.json",
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
        "phase7_11_report_sha256",
        "phase7_10_report_sha256",
        "future_executor_approval_review_packet_sha256",
        "future_executor_approval_review_guard_report_sha256",
        "future_executor_enablement_design_packet_sha256",
        "future_executor_enablement_design_guard_report_sha256",
        "future_executor_approval_intake_validation_record_sha256",
        "future_executor_prerequisite_packet_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("record_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _build_enablement_design_packet(*, report_id: str, artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase7_10 = artifacts.get("phase7_10_approval_review_packet", {})
    review_packet = artifacts.get("future_executor_approval_review_packet", {})
    review_guard = artifacts.get("future_executor_approval_review_guard", {})
    intake_record = artifacts.get("future_executor_approval_intake_validation_record", {})
    prerequisite_packet = artifacts.get("future_executor_prerequisite_packet", {})
    source_hash_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    return {
        "packet_type": "future_signed_testnet_executor_enablement_design_packet_review_only",
        "phase7_11_version": PHASE7_11_VERSION,
        "source_phase7_11_report_id": report_id,
        "source_phase7_10_report_id": phase7_10.get("phase7_10_future_executor_approval_review_packet_id"),
        "review_only": True,
        "enablement_design_only": True,
        "not_runtime_authority": True,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "approval_review_packet_ready": phase7_10.get("phase7_10_review_packet_ready") is True,
        "approval_review_guard_passed": review_guard.get("guard_passed") is True,
        "metadata_only_key_reference_validated_review_only": review_packet.get("metadata_only_key_reference_validated_review_only") is True,
        "prerequisite_packet_hash_matches": review_packet.get("prerequisite_packet_hash_matches") is True,
        "future_executor_approval_intake_validated_review_only": review_packet.get("future_executor_approval_intake_validated_review_only") is True,
        "intake_validation_record_hash": sha256_json(dict(intake_record or {})) if intake_record else None,
        "approval_review_packet_hash": sha256_json(dict(review_packet or {})) if review_packet else None,
        "approval_review_guard_hash": sha256_json(dict(review_guard or {})) if review_guard else None,
        "prerequisite_packet_hash": sha256_json(dict(prerequisite_packet or {})) if prerequisite_packet else None,
        "enablement_design_scope": [
            "disabled_executor_flag_review",
            "metadata_only_key_reference_review",
            "fresh_pre_submit_payload_validation_design",
            "fresh_pre_order_risk_gate_recheck_design",
            "manual_kill_switch_confirmation_design",
            "hard_cap_min_max_notional_fee_slippage_design",
            "venue_readiness_evidence_design",
            "idempotency_key_requirement_design",
            "reconciliation_and_session_close_requirement_design",
        ],
        "future_enablement_prerequisites": [
            "Separate future Phase 7 executor enablement review must be created before any executor can be considered.",
            "Fresh would-submit payload validation must be generated after this design review.",
            "Fresh PreOrderRiskGate recheck must happen immediately before any later executor review.",
            "Manual kill switch confirmation must be recorded immediately before any later executor review.",
            "Only metadata-only key references and fingerprints may be used; key values remain forbidden.",
            "Venue readiness evidence must remain review-only until a later approved stage.",
            "Reconciliation and session close evidence are mandatory for any future testnet session.",
        ],
        "forbidden_scope": [
            "actual_executor_enablement",
            "actual_signed_testnet_order_submission",
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


def _build_enablement_design_guard(*, report_id: str, packet: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    source_flags = _unsafe_flags_by_artifact(artifacts)
    packet_flags = _unsafe_fields(packet)
    all_flags = dict(source_flags)
    if packet_flags:
        all_flags["future_executor_enablement_design_packet"] = packet_flags
    missing: list[str] = []
    if packet.get("review_only") is not True:
        missing.append("ENABLEMENT_DESIGN_PACKET_NOT_REVIEW_ONLY")
    if packet.get("approval_review_packet_ready") is not True:
        missing.append("APPROVAL_REVIEW_PACKET_NOT_READY")
    if packet.get("approval_review_guard_passed") is not True:
        missing.append("APPROVAL_REVIEW_GUARD_NOT_PASSED")
    if packet.get("metadata_only_key_reference_validated_review_only") is not True:
        missing.append("METADATA_ONLY_KEY_REFERENCE_NOT_VALIDATED")
    if packet.get("prerequisite_packet_hash_matches") is not True:
        missing.append("PREREQUISITE_PACKET_HASH_NOT_MATCHED")
    if packet.get("future_executor_approval_intake_validated_review_only") is not True:
        missing.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_NOT_VALIDATED_REVIEW_ONLY")
    guard_passed = not all_flags and not missing
    return {
        "guard_type": "future_signed_testnet_executor_enablement_design_guard_review_only",
        "phase7_11_version": PHASE7_11_VERSION,
        "source_phase7_11_report_id": report_id,
        "review_only": True,
        "enablement_design_guard_only": True,
        "guard_passed": guard_passed,
        "missing_enablement_design_prerequisites": missing,
        "unsafe_flags_by_artifact": all_flags,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
        "requires_later_explicit_executor_enablement_review": True,
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
            "# Phase 7.11 Future Executor Enablement Design Review — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase creates a future executor enablement design packet from Phase 7.10 approval review evidence. It is not executor enablement, not runtime approval, and not order submission authority.",
            "",
            "## Result",
            "",
            f"- Design ready: `{report.get('phase7_11_enablement_design_ready')}`",
            f"- Design packet created: `{report.get('future_executor_enablement_design_packet_created')}`",
            f"- Design guard passed: `{report.get('enablement_design_guard_passed')}`",
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
            f"`{report.get('phase7_11_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_11_future_executor_enablement_design_review_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_10_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_10_first:
        persist_phase7_10_future_executor_approval_review_packet_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    phase7_10 = artifacts.get("phase7_10_approval_review_packet", {})
    review_packet = artifacts.get("future_executor_approval_review_packet", {})
    review_guard = artifacts.get("future_executor_approval_review_guard", {})

    preliminary_id = stable_id("phase7_11_future_executor_enablement_design_review", {"source_summary": source_summary, "created_at_utc": created}, 24)
    packet = _build_enablement_design_packet(report_id=preliminary_id, artifacts=artifacts, created_at_utc=created)
    guard = _build_enablement_design_guard(report_id=preliminary_id, packet=packet, artifacts=artifacts, created_at_utc=created)

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_11_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_11_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_10.get("status") != "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_10_APPROVAL_REVIEW_PACKET_NOT_READY")
    if phase7_10.get("phase7_10_review_packet_ready") is not True:
        blockers.append("PHASE7_10_APPROVAL_REVIEW_NOT_READY")
    if review_packet.get("packet_type") != "future_signed_testnet_executor_approval_review_packet_review_only":
        blockers.append("FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_INVALID")
    if review_guard.get("guard_type") != "future_signed_testnet_executor_approval_review_guard_review_only":
        blockers.append("FUTURE_EXECUTOR_APPROVAL_REVIEW_GUARD_INVALID")
    if review_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_REVIEW_GUARD_NOT_PASSED")
    if guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_DESIGN_GUARD_NOT_PASSED")
        blockers.extend(guard.get("missing_enablement_design_prerequisites") or [])

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_11_future_executor_enablement_design_review",
        {
            "source_summary": source_summary,
            "packet_hash": sha256_json(packet),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    packet = {**packet, "source_phase7_11_report_id": report_id}
    guard = {**guard, "source_phase7_11_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_11_future_executor_enablement_design_review_id": report_id,
        "phase7_11_version": PHASE7_11_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "enablement_design_only": True,
        "phase7_11_enablement_design_ready": ready,
        "future_executor_enablement_design_packet_created": True,
        "future_executor_enablement_design_guard_created": True,
        "enablement_design_guard_passed": guard.get("guard_passed") is True,
        "phase7_10_review_packet_ready": phase7_10.get("phase7_10_review_packet_ready") is True,
        "approval_review_guard_passed": review_guard.get("guard_passed") is True,
        "metadata_only_key_reference_validated_review_only": packet.get("metadata_only_key_reference_validated_review_only") is True,
        "prerequisite_packet_hash_matches": packet.get("prerequisite_packet_hash_matches") is True,
        "future_executor_approval_intake_validated_review_only": packet.get("future_executor_approval_intake_validated_review_only") is True,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "future_explicit_executor_enablement_review_required": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "metadata_only_key_reference_required": True,
        "venue_readiness_evidence_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_11_allowed_next_scope": "future_executor_enablement_guard_fixture_still_disabled" if ready else "resolve_phase7_11_enablement_design_blockers",
        "recommended_next_action": "prepare_phase7_12_future_executor_enablement_guard_fixture_keep_execution_disabled" if ready else "inspect_phase7_11_blockers_and_rerun_phase7_10_phase7_11",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
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
    packet["future_executor_enablement_design_packet_sha256"] = sha256_json(packet)
    guard["future_executor_enablement_design_guard_report_sha256"] = sha256_json(guard)
    report["future_executor_enablement_design_packet_sha256"] = packet["future_executor_enablement_design_packet_sha256"]
    report["future_executor_enablement_design_guard_report_sha256"] = guard["future_executor_enablement_design_guard_report_sha256"]
    report["phase7_11_report_sha256"] = sha256_json(report)
    return report, packet, guard


def persist_phase7_11_future_executor_enablement_design_review_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_10_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_11_future_executor_enablement_design_review")
    report, packet, guard = build_phase7_11_future_executor_enablement_design_review_report(cfg=cfg, run_phase7_10_first=run_phase7_10_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_11_future_executor_enablement_design_review_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_enablement_design_packet_review_only.json", packet)
    atomic_write_json(latest / "future_signed_testnet_executor_enablement_design_guard_report.json", guard)
    (latest / "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_DESIGN_REVIEW_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(phase_dir / "phase7_11_future_executor_enablement_design_review_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_enablement_design_packet_review_only.json", packet)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_enablement_design_guard_report.json", guard)
    (phase_dir / "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_DESIGN_REVIEW_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_11_REGISTRY_NAME),
        {
            "phase7_11_future_executor_enablement_design_review_id": report.get("phase7_11_future_executor_enablement_design_review_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_11_enablement_design_ready": report.get("phase7_11_enablement_design_ready"),
            "enablement_design_guard_passed": report.get("enablement_design_guard_passed"),
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
        registry_name=PHASE7_11_REGISTRY_NAME,
        id_field="phase7_11_future_executor_enablement_design_review_registry_record_id",
        hash_field="phase7_11_future_executor_enablement_design_review_registry_record_sha256",
        id_prefix="phase7_11_future_executor_enablement_design_review_registry_record",
    )
    atomic_write_json(latest / "phase7_11_future_executor_enablement_design_review_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_11_future_executor_enablement_design_review_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_11_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_11_future_executor_enablement_design_review_report",
    "persist_phase7_11_future_executor_enablement_design_review_report",
]
