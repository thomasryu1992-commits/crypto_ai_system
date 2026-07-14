from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.enablement_review import (
    persist_phase7_13_future_executor_enablement_review_packet_report,
)

PHASE7_14_VERSION = "phase7_14_future_executor_operator_decision_packet_v1"
PHASE7_14_REGISTRY_NAME = "phase7_14_future_executor_operator_decision_packet_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_13_enablement_review_packet_report": "phase7_13_future_executor_enablement_review_packet_report.json",
    "future_executor_enablement_review_packet": "future_signed_testnet_executor_enablement_review_packet_review_only.json",
    "future_executor_enablement_review_guard": "future_signed_testnet_executor_enablement_review_guard_report.json",
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

REQUIRED_DECISION_PACKET_FIELDS = [
    "packet_type",
    "review_only",
    "operator_decision_packet_only",
    "not_runtime_authority",
    "source_phase7_14_report_id",
    "source_phase7_13_report_id",
    "source_phase7_13_report_hash",
    "source_enablement_review_packet_hash",
    "source_enablement_review_guard_hash",
    "operator_decision_options",
    "required_before_any_future_executor_enablement",
    "metadata_only_key_reference_required",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "manual_kill_switch_confirmation_required",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
    "future_operator_decision_required_before_any_order",
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
        "phase7_14_report_sha256",
        "phase7_13_report_sha256",
        "future_executor_enablement_review_packet_sha256",
        "future_executor_enablement_review_guard_report_sha256",
        "future_executor_operator_decision_packet_sha256",
        "future_executor_operator_decision_guard_report_sha256",
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


def validate_operator_decision_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_DECISION_PACKET_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_OPERATOR_DECISION_PACKET_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_OPERATOR_DECISION_PACKET_FLAGS:" + ",".join(unsafe))
    if data.get("packet_type") != "future_signed_testnet_executor_operator_decision_packet_review_only":
        blockers.append("INVALID_OPERATOR_DECISION_PACKET_TYPE")
    if data.get("review_only") is not True:
        blockers.append("OPERATOR_DECISION_PACKET_NOT_REVIEW_ONLY")
    if data.get("operator_decision_packet_only") is not True:
        blockers.append("OPERATOR_DECISION_PACKET_NOT_PACKET_ONLY")
    if data.get("not_runtime_authority") is not True:
        blockers.append("OPERATOR_DECISION_PACKET_RUNTIME_AUTHORITY_NOT_BLOCKED")
    options = data.get("operator_decision_options")
    if not isinstance(options, list) or not options:
        blockers.append("OPERATOR_DECISION_OPTIONS_MISSING")
    for field in (
        "required_before_any_future_executor_enablement",
        "metadata_only_key_reference_required",
        "fresh_pre_submit_payload_validation_required",
        "fresh_pre_order_risk_gate_recheck_required",
        "manual_kill_switch_confirmation_required",
        "hard_caps_rechecked",
        "pre_order_risk_gate_rechecked",
        "reconciliation_required_after_any_session",
        "session_close_report_required",
        "future_operator_decision_required_before_any_order",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_OPERATOR_DECISION_CONFIRMATION_NOT_TRUE:{field}")
    valid = not blockers
    return {
        "packet_valid_review_only": valid,
        "packet_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "packet_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_operator_decision_packet(*, report_id: str, artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase7_13 = artifacts.get("phase7_13_enablement_review_packet_report", {})
    review_packet = artifacts.get("future_executor_enablement_review_packet", {})
    review_guard = artifacts.get("future_executor_enablement_review_guard", {})
    packet: dict[str, Any] = {
        "packet_type": "future_signed_testnet_executor_operator_decision_packet_review_only",
        "phase7_14_version": PHASE7_14_VERSION,
        "source_phase7_14_report_id": report_id,
        "source_phase7_13_report_id": phase7_13.get("phase7_13_future_executor_enablement_review_packet_id"),
        "review_only": True,
        "operator_decision_packet_only": True,
        "not_runtime_authority": True,
        "source_phase7_13_report_hash": _artifact_hash(phase7_13),
        "source_enablement_review_packet_hash": _artifact_hash(review_packet),
        "source_enablement_review_guard_hash": _artifact_hash(review_guard),
        "operator_decision_options": [
            "APPROVE_FUTURE_EXECUTOR_REVIEW_ONLY_NOT_ENABLEMENT",
            "DEFER_FUTURE_EXECUTOR_REVIEW",
            "REJECT_FUTURE_EXECUTOR_REVIEW",
        ],
        "operator_decision_required_fields_for_future_intake": [
            "operator_decision_id",
            "operator_id",
            "operator_ticket_or_signature",
            "canonical_utc_timestamp",
            "decision_option",
            "source_phase7_14_report_hash",
            "source_enablement_review_packet_hash",
            "source_enablement_review_guard_hash",
            "metadata_only_key_reference_id",
            "metadata_only_key_fingerprint",
            "max_testnet_notional_usd",
            "max_testnet_order_count",
            "max_testnet_daily_loss_usd",
            "manual_kill_switch_confirmation",
            "hard_caps_rechecked",
            "pre_order_risk_gate_rechecked",
            "fresh_pre_submit_payload_validation_required",
            "reconciliation_required_after_any_session",
            "session_close_report_required",
        ],
        "decision_scope": [
            "operator_decision_for_future_executor_review_only",
            "metadata_only_key_reference_policy_review",
            "hard_cap_kill_switch_pre_order_risk_gate_review",
            "reconciliation_session_close_requirement_review",
            "disabled_executor_flags_review",
        ],
        "required_before_any_future_executor_enablement": True,
        "metadata_only_key_reference_required": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "hard_caps_rechecked": True,
        "pre_order_risk_gate_rechecked": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "future_operator_decision_required_before_any_order": True,
        "actual_operator_decision_recorded": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }
    packet["future_executor_operator_decision_packet_sha256"] = sha256_json(packet)
    return packet


def _build_decision_guard(*, report_id: str, decision_packet: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    validation = validate_operator_decision_packet(decision_packet)
    return {
        "guard_type": "future_signed_testnet_executor_operator_decision_guard_review_only",
        "phase7_14_version": PHASE7_14_VERSION,
        "source_phase7_14_report_id": report_id,
        "review_only": True,
        "operator_decision_guard_only": True,
        "guard_passed": validation.get("packet_valid_review_only") is True,
        "operator_decision_packet_validation": validation,
        "source_phase7_13_review_packet_ready": artifacts.get("phase7_13_enablement_review_packet_report", {}).get("phase7_13_review_packet_ready") is True,
        "source_enablement_review_guard_passed": artifacts.get("future_executor_enablement_review_guard", {}).get("guard_passed") is True,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
        "actual_operator_decision_recorded": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join([
        "# Phase 7.14 Future Executor Operator Decision Packet — Review Only",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This phase packages Phase 7.13 future executor enablement review evidence into an operator decision packet. It does not record an actual operator decision, enable the executor, or submit orders.",
        "",
        "## Result",
        "",
        f"- Operator decision packet ready: `{report.get('phase7_14_operator_decision_packet_ready')}`",
        f"- Operator decision guard passed: `{report.get('operator_decision_guard_passed')}`",
        f"- Future operator decision required before any order: `{report.get('future_operator_decision_required_before_any_order')}`",
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
    ])


def build_phase7_14_future_executor_operator_decision_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_13_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_13_first:
        persist_phase7_13_future_executor_enablement_review_packet_report(cfg=cfg)
    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    preliminary_id = stable_id("phase7_14_future_executor_operator_decision_packet", {"source_summary": source_summary, "created_at_utc": created}, 24)
    decision_packet = _build_operator_decision_packet(report_id=preliminary_id, artifacts=artifacts, created_at_utc=created)
    decision_guard = _build_decision_guard(report_id=preliminary_id, decision_packet=decision_packet, artifacts=artifacts, created_at_utc=created)
    phase7_13 = artifacts.get("phase7_13_enablement_review_packet_report", {})
    review_packet = artifacts.get("future_executor_enablement_review_packet", {})
    review_guard = artifacts.get("future_executor_enablement_review_guard", {})

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_14_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_14_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_13.get("status") != "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_13_ENABLEMENT_REVIEW_PACKET_NOT_READY")
    if phase7_13.get("phase7_13_review_packet_ready") is not True:
        blockers.append("PHASE7_13_REVIEW_PACKET_READY_FALSE")
    if review_packet.get("packet_type") != "future_signed_testnet_executor_enablement_review_packet_review_only":
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_INVALID")
    if review_guard.get("guard_type") != "future_signed_testnet_executor_enablement_review_guard_review_only":
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_REVIEW_GUARD_INVALID")
    if review_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_REVIEW_GUARD_NOT_PASSED")
    if decision_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_OPERATOR_DECISION_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_14_future_executor_operator_decision_packet",
        {"source_summary": source_summary, "decision_packet_hash": sha256_json(decision_packet), "decision_guard_hash": sha256_json(decision_guard), "blockers": blockers, "created_at_utc": created},
        24,
    )
    decision_packet["source_phase7_14_report_id"] = report_id
    decision_guard["source_phase7_14_report_id"] = report_id
    decision_packet["future_executor_operator_decision_packet_sha256"] = sha256_json(decision_packet)
    decision_guard["future_executor_operator_decision_guard_report_sha256"] = sha256_json(decision_guard)
    report: dict[str, Any] = {
        "phase7_14_future_executor_operator_decision_packet_id": report_id,
        "phase7_14_version": PHASE7_14_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "operator_decision_packet_only": True,
        "phase7_14_operator_decision_packet_ready": ready,
        "future_executor_operator_decision_packet_created": True,
        "future_executor_operator_decision_guard_report_created": True,
        "operator_decision_guard_passed": decision_guard.get("guard_passed") is True,
        "future_operator_decision_required_before_any_order": True,
        "actual_operator_decision_recorded": False,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_14_allowed_next_scope": "future_executor_operator_decision_intake_template_still_disabled" if ready else "resolve_phase7_14_operator_decision_packet_blockers",
        "recommended_next_action": "prepare_phase7_15_operator_decision_intake_template_keep_execution_disabled" if ready else "inspect_phase7_14_blockers_and_rerun_phase7_13_phase7_14",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
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
    report["future_executor_operator_decision_packet_sha256"] = decision_packet["future_executor_operator_decision_packet_sha256"]
    report["future_executor_operator_decision_guard_report_sha256"] = decision_guard["future_executor_operator_decision_guard_report_sha256"]
    report["phase7_14_report_sha256"] = sha256_json(report)
    return report, decision_packet, decision_guard


def persist_phase7_14_future_executor_operator_decision_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_13_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_14_future_executor_operator_decision_packet")
    report, decision_packet, decision_guard = build_phase7_14_future_executor_operator_decision_packet_report(cfg=cfg, run_phase7_13_first=run_phase7_13_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_14_future_executor_operator_decision_packet_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_operator_decision_packet_review_only.json", decision_packet)
    atomic_write_json(latest / "future_signed_testnet_executor_operator_decision_guard_report.json", decision_guard)
    (latest / "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(phase_dir / "phase7_14_future_executor_operator_decision_packet_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_operator_decision_packet_review_only.json", decision_packet)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_operator_decision_guard_report.json", decision_guard)
    (phase_dir / "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_14_REGISTRY_NAME),
        {
            "phase7_14_future_executor_operator_decision_packet_id": report.get("phase7_14_future_executor_operator_decision_packet_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_14_operator_decision_packet_ready": report.get("phase7_14_operator_decision_packet_ready"),
            "operator_decision_guard_passed": report.get("operator_decision_guard_passed"),
            "actual_operator_decision_recorded": False,
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
        registry_name=PHASE7_14_REGISTRY_NAME,
        id_field="phase7_14_future_executor_operator_decision_packet_registry_record_id",
        hash_field="phase7_14_future_executor_operator_decision_packet_registry_record_sha256",
        id_prefix="phase7_14_future_executor_operator_decision_packet_registry_record",
    )
    atomic_write_json(latest / "phase7_14_future_executor_operator_decision_packet_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_14_future_executor_operator_decision_packet_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_14_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "validate_operator_decision_packet",
    "build_phase7_14_future_executor_operator_decision_packet_report",
    "persist_phase7_14_future_executor_operator_decision_packet_report",
]
