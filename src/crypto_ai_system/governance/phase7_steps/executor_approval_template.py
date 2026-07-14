from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.executor_prerequisite import (
    persist_phase7_7_future_executor_review_prerequisite_design_report,
)

PHASE7_8_VERSION = "phase7_8_future_executor_approval_packet_template_v1"
PHASE7_8_REGISTRY_NAME = "phase7_8_future_executor_approval_packet_template_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_TEMPLATE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_TEMPLATE_BLOCKED_REVIEW_ONLY"

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

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_7_prerequisite_design": "phase7_7_future_executor_review_prerequisite_design_report.json",
    "future_executor_prerequisite_packet": "future_signed_testnet_executor_review_prerequisite_packet_review_only.json",
    "future_executor_prerequisite_guard": "future_signed_testnet_executor_review_prerequisite_guard_report.json",
}

OPERATOR_REQUIRED_FIELDS = [
    "executor_approval_packet_id",
    "operator_id",
    "operator_ticket_or_signature",
    "canonical_utc_timestamp",
    "approved_profile_id",
    "approved_profile_hash",
    "approval_intake_id",
    "approval_packet_id",
    "prerequisite_packet_hash",
    "metadata_only_key_reference_id",
    "metadata_only_key_fingerprint",
    "max_testnet_notional_usd",
    "max_testnet_order_count",
    "max_testnet_daily_loss_usd",
    "kill_switch_rechecked",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
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
        "phase7_8_report_sha256",
        "phase7_7_report_sha256",
        "future_executor_prerequisite_packet_sha256",
        "future_executor_prerequisite_guard_report_sha256",
        "future_executor_approval_template_sha256",
        "future_executor_approval_template_guard_report_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _extract_profile_context(prerequisite_packet: Mapping[str, Any], phase7_7: Mapping[str, Any]) -> tuple[str, str, str, str]:
    # Phase 7.7 is prerequisite-focused and does not grant approval. These fields are placeholders
    # for a future human-filled executor approval packet, but we carry stable upstream context when present.
    source_summary = phase7_7.get("source_evidence_hash_summary") or prerequisite_packet.get("source_evidence_hash_summary") or {}
    profile_id = "MANUAL_REQUIRED_APPROVED_PROFILE_ID"
    profile_hash = "MANUAL_REQUIRED_APPROVED_PROFILE_HASH"
    approval_intake_id = "MANUAL_REQUIRED_APPROVAL_INTAKE_ID"
    approval_packet_id = "MANUAL_REQUIRED_APPROVAL_PACKET_ID"
    # Opportunistically preserve values if older reports expose them.
    for payload in (phase7_7, prerequisite_packet, source_summary):
        if isinstance(payload, Mapping):
            profile_id = str(payload.get("approved_profile_id") or payload.get("profile_id") or profile_id)
            profile_hash = str(payload.get("approved_profile_hash") or payload.get("profile_candidate_hash") or profile_hash)
            approval_intake_id = str(payload.get("approval_intake_id") or approval_intake_id)
            approval_packet_id = str(payload.get("approval_packet_id") or approval_packet_id)
    return profile_id, profile_hash, approval_intake_id, approval_packet_id


def _build_executor_approval_template(*, report_id: str, phase7_7: Mapping[str, Any], prerequisite_packet: Mapping[str, Any], prerequisite_guard: Mapping[str, Any], created_at_utc: str) -> dict[str, Any]:
    prerequisite_hash = sha256_json(dict(prerequisite_packet or {})) if prerequisite_packet else "MANUAL_REQUIRED_PREREQUISITE_PACKET_HASH"
    profile_id, profile_hash, approval_intake_id, approval_packet_id = _extract_profile_context(prerequisite_packet, phase7_7)
    template: dict[str, Any] = {
        "template_type": "future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY",
        "phase7_8_version": PHASE7_8_VERSION,
        "source_phase7_8_report_id": report_id,
        "source_phase7_7_report_id": phase7_7.get("phase7_7_future_executor_review_prerequisite_design_id"),
        "source_prerequisite_packet_hash": prerequisite_hash,
        "source_prerequisite_guard_passed": prerequisite_guard.get("guard_passed") is True,
        "review_only": True,
        "template_only": True,
        "not_runtime_authority": True,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "executor_approval_packet_id": "MANUAL_REQUIRED_EXECUTOR_APPROVAL_PACKET_ID",
        "operator_id": "MANUAL_REQUIRED_OPERATOR_ID",
        "operator_ticket_or_signature": "MANUAL_REQUIRED_OPERATOR_TICKET_OR_SIGNATURE",
        "canonical_utc_timestamp": "MANUAL_REQUIRED_CANONICAL_UTC_TIMESTAMP",
        "approved_profile_id": profile_id,
        "approved_profile_hash": profile_hash,
        "approval_intake_id": approval_intake_id,
        "approval_packet_id": approval_packet_id,
        "prerequisite_packet_hash": prerequisite_hash,
        "metadata_only_key_reference_id": "MANUAL_REQUIRED_METADATA_ONLY_KEY_REFERENCE_ID",
        "metadata_only_key_fingerprint": "MANUAL_REQUIRED_METADATA_ONLY_KEY_FINGERPRINT",
        "max_testnet_notional_usd": "MANUAL_REQUIRED_NUMERIC_MAX_TESTNET_NOTIONAL_USD",
        "max_testnet_order_count": "MANUAL_REQUIRED_INTEGER_MAX_TESTNET_ORDER_COUNT",
        "max_testnet_daily_loss_usd": "MANUAL_REQUIRED_NUMERIC_MAX_TESTNET_DAILY_LOSS_USD",
        "kill_switch_rechecked": "MANUAL_REQUIRED_BOOLEAN_TRUE",
        "hard_caps_rechecked": "MANUAL_REQUIRED_BOOLEAN_TRUE",
        "pre_order_risk_gate_rechecked": "MANUAL_REQUIRED_BOOLEAN_TRUE",
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "operator_required_fields": OPERATOR_REQUIRED_FIELDS,
        "operator_fill_instructions": [
            "Fill only MANUAL_REQUIRED_* fields before a later Phase 7.9 intake validation.",
            "Do not set any executor/order/runtime flag to true.",
            "Use metadata-only key reference and fingerprint; never paste API key or secret values.",
            "Run fresh pre-submit payload validation and PreOrderRiskGate recheck after this template is completed.",
        ],
        "forbidden_scope": [
            "actual_signed_testnet_order_submission",
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
    template["future_executor_approval_template_sha256"] = sha256_json(template)
    return template


def _build_template_guard(*, report_id: str, template: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    template_flags = _unsafe_fields(template)
    source_flags = _unsafe_flags_by_artifact(artifacts)
    missing_fields = [field for field in OPERATOR_REQUIRED_FIELDS if field not in template]
    all_flags: dict[str, list[str]] = dict(source_flags)
    if template_flags:
        all_flags["future_executor_approval_template"] = template_flags
    guard_passed = not all_flags and not missing_fields and template.get("review_only") is True and template.get("template_only") is True
    return {
        "guard_type": "future_signed_testnet_executor_approval_template_guard_review_only",
        "phase7_8_version": PHASE7_8_VERSION,
        "source_phase7_8_report_id": report_id,
        "review_only": True,
        "template_only": True,
        "guard_passed": guard_passed,
        "template_contains_operator_required_fields": not missing_fields,
        "missing_operator_required_fields": missing_fields,
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
            "# Phase 7.8 Future Executor Approval Packet Template — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase creates a review-only template for a possible future signed testnet executor approval packet. It does not approve an executor, enable execution, submit orders, read secrets, mutate settings, or promote to testnet/live.",
            "",
            "## Result",
            "",
            f"- Template created: `{report.get('future_executor_approval_template_created')}`",
            f"- Template guard passed: `{report.get('template_guard_passed')}`",
            f"- Phase 7.8 ready: `{report.get('phase7_8_template_ready')}`",
            "",
            "## Operator Required Fields",
            "",
            *[f"- `{item}`" for item in OPERATOR_REQUIRED_FIELDS],
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
            f"`{report.get('phase7_8_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_8_future_executor_approval_packet_template_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_7_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_7_first:
        persist_phase7_7_future_executor_review_prerequisite_design_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    phase7_7 = artifacts.get("phase7_7_prerequisite_design", {})
    prerequisite_packet = artifacts.get("future_executor_prerequisite_packet", {})
    prerequisite_guard = artifacts.get("future_executor_prerequisite_guard", {})

    preliminary_id = stable_id("phase7_8_future_executor_approval_packet_template", {"source_summary": source_summary, "created_at_utc": created}, 24)
    template = _build_executor_approval_template(
        report_id=preliminary_id,
        phase7_7=phase7_7,
        prerequisite_packet=prerequisite_packet,
        prerequisite_guard=prerequisite_guard,
        created_at_utc=created,
    )
    guard = _build_template_guard(report_id=preliminary_id, template=template, artifacts=artifacts, created_at_utc=created)

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_8_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_8_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_7.get("status") != "PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_RECORDED_REVIEW_ONLY" or phase7_7.get("phase7_7_prerequisite_design_ready") is not True:
        blockers.append("PHASE7_7_PREREQUISITE_DESIGN_NOT_READY")
    if phase7_7.get("future_executor_review_prerequisites_ready_review_only") is not True:
        blockers.append("FUTURE_EXECUTOR_REVIEW_PREREQUISITES_NOT_READY")
    if prerequisite_packet.get("packet_type") != "future_signed_testnet_executor_review_prerequisite_packet_review_only":
        blockers.append("PREREQUISITE_PACKET_INVALID")
    if prerequisite_packet.get("future_executor_review_prerequisites_ready_review_only") is not True:
        blockers.append("PREREQUISITE_PACKET_NOT_READY")
    if prerequisite_packet.get("executor_enablement_authority") is not False:
        blockers.append("PREREQUISITE_PACKET_EXECUTOR_AUTHORITY_NOT_FALSE")
    if prerequisite_guard.get("guard_type") != "future_signed_testnet_executor_review_prerequisite_guard_review_only":
        blockers.append("PREREQUISITE_GUARD_INVALID")
    if prerequisite_guard.get("guard_passed") is not True:
        blockers.append("PREREQUISITE_GUARD_NOT_PASSED")
    template_flags = _unsafe_fields(template)
    if template_flags:
        blockers.append(f"UNSAFE_PHASE7_8_TEMPLATE_FLAGS:{','.join(template_flags)}")
    if guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_TEMPLATE_GUARD_NOT_PASSED")
    if guard.get("template_contains_operator_required_fields") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_TEMPLATE_REQUIRED_FIELDS_MISSING")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_8_future_executor_approval_packet_template",
        {
            "source_summary": source_summary,
            "template_hash": sha256_json(template),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    template = {**template, "source_phase7_8_report_id": report_id}
    guard = {**guard, "source_phase7_8_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_8_future_executor_approval_packet_template_id": report_id,
        "phase7_8_version": PHASE7_8_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "template_only": True,
        "phase7_8_template_ready": ready,
        "future_executor_approval_template_created": True,
        "template_guard_created": True,
        "template_guard_passed": guard.get("guard_passed") is True,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "phase7_7_prerequisite_design_ready": phase7_7.get("phase7_7_prerequisite_design_ready") is True,
        "future_executor_review_prerequisites_ready_review_only": phase7_7.get("future_executor_review_prerequisites_ready_review_only") is True,
        "metadata_only_key_reference_required": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "executor_approval_template_operator_required_fields": OPERATOR_REQUIRED_FIELDS,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_8_allowed_next_scope": "future_executor_approval_intake_validator_still_disabled" if ready else "resolve_phase7_8_template_blockers",
        "recommended_next_action": "prepare_phase7_9_future_executor_approval_intake_validator_keep_execution_disabled" if ready else "inspect_phase7_8_blockers_and_rerun_phase7_7_phase7_8",
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
    report["future_executor_approval_template_sha256"] = sha256_json(template)
    report["future_executor_approval_template_guard_report_sha256"] = sha256_json(guard)
    report["phase7_8_report_sha256"] = sha256_json(report)
    return report, template, guard


def persist_phase7_8_future_executor_approval_packet_template_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_7_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_8_future_executor_approval_packet_template")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, guard = build_phase7_8_future_executor_approval_packet_template_report(cfg=cfg, run_phase7_7_first=run_phase7_7_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_8_future_executor_approval_packet_template_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(latest / "future_signed_testnet_executor_approval_template_guard_report.json", guard)
    (latest / "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_TEMPLATE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(signed_testnet_dir / "future_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json", template)

    atomic_write_json(phase_dir / "phase7_8_future_executor_approval_packet_template_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_approval_template_guard_report.json", guard)
    (phase_dir / "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_TEMPLATE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_8_REGISTRY_NAME),
        {
            "phase7_8_future_executor_approval_packet_template_id": report.get("phase7_8_future_executor_approval_packet_template_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_8_template_ready": report.get("phase7_8_template_ready"),
            "future_executor_approval_template_created": report.get("future_executor_approval_template_created"),
            "template_guard_passed": report.get("template_guard_passed"),
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
        registry_name=PHASE7_8_REGISTRY_NAME,
        id_field="phase7_8_future_executor_approval_packet_template_registry_record_id",
        hash_field="phase7_8_future_executor_approval_packet_template_registry_record_sha256",
        id_prefix="phase7_8_future_executor_approval_packet_template_registry_record",
    )
    atomic_write_json(latest / "phase7_8_future_executor_approval_packet_template_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_8_future_executor_approval_packet_template_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_8_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "OPERATOR_REQUIRED_FIELDS",
    "build_phase7_8_future_executor_approval_packet_template_report",
    "persist_phase7_8_future_executor_approval_packet_template_report",
]
