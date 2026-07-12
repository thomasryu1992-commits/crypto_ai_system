from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_12_future_executor_enablement_guard_fixture import (
    persist_phase7_12_future_executor_enablement_guard_fixture_report,
)

PHASE7_13_VERSION = "phase7_13_future_executor_enablement_review_packet_v1"
PHASE7_13_REGISTRY_NAME = "phase7_13_future_executor_enablement_review_packet_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_12_enablement_guard_fixture_report": "phase7_12_future_executor_enablement_guard_fixture_report.json",
    "future_executor_enablement_guard_valid_fixture": "future_signed_testnet_executor_enablement_guard_valid_fixture_review_only.json",
    "future_executor_enablement_guard_fixture_guard": "future_signed_testnet_executor_enablement_guard_fixture_guard_report.json",
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

REQUIRED_REVIEW_PACKET_FIELDS = [
    "packet_type",
    "review_only",
    "enablement_review_only",
    "not_runtime_authority",
    "source_phase7_13_report_id",
    "source_phase7_12_report_id",
    "source_phase7_12_report_hash",
    "source_enablement_guard_valid_fixture_hash",
    "source_enablement_guard_fixture_guard_hash",
    "metadata_only_key_reference_required",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "manual_kill_switch_confirmation_required",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
    "future_executor_enablement_review_required_before_any_order",
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
        "phase7_13_report_sha256",
        "phase7_12_report_sha256",
        "future_executor_enablement_guard_valid_fixture_sha256",
        "future_executor_enablement_guard_fixture_guard_report_sha256",
        "future_executor_enablement_review_packet_sha256",
        "future_executor_enablement_review_guard_report_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("fixture_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def validate_enablement_review_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_REVIEW_PACKET_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_ENABLEMENT_REVIEW_PACKET_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_ENABLEMENT_REVIEW_PACKET_FLAGS:" + ",".join(unsafe))
    if data.get("packet_type") != "future_signed_testnet_executor_enablement_review_packet_review_only":
        blockers.append("INVALID_ENABLEMENT_REVIEW_PACKET_TYPE")
    if data.get("review_only") is not True:
        blockers.append("ENABLEMENT_REVIEW_PACKET_NOT_REVIEW_ONLY")
    if data.get("enablement_review_only") is not True:
        blockers.append("ENABLEMENT_REVIEW_PACKET_NOT_REVIEW_ONLY_SCOPE")
    if data.get("not_runtime_authority") is not True:
        blockers.append("ENABLEMENT_REVIEW_PACKET_RUNTIME_AUTHORITY_NOT_BLOCKED")
    for field in (
        "metadata_only_key_reference_required",
        "fresh_pre_submit_payload_validation_required",
        "fresh_pre_order_risk_gate_recheck_required",
        "manual_kill_switch_confirmation_required",
        "hard_caps_rechecked",
        "pre_order_risk_gate_rechecked",
        "reconciliation_required_after_any_session",
        "session_close_report_required",
        "future_executor_enablement_review_required_before_any_order",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_ENABLEMENT_REVIEW_CONFIRMATION_NOT_TRUE:{field}")
    valid = not blockers
    return {
        "packet_valid_review_only": valid,
        "packet_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "packet_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_review_packet(*, report_id: str, artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase7_12 = artifacts.get("phase7_12_enablement_guard_fixture_report", {})
    valid_fixture = artifacts.get("future_executor_enablement_guard_valid_fixture", {})
    fixture_guard = artifacts.get("future_executor_enablement_guard_fixture_guard", {})
    packet: dict[str, Any] = {
        "packet_type": "future_signed_testnet_executor_enablement_review_packet_review_only",
        "phase7_13_version": PHASE7_13_VERSION,
        "source_phase7_13_report_id": report_id,
        "source_phase7_12_report_id": phase7_12.get("phase7_12_future_executor_enablement_guard_fixture_id"),
        "review_only": True,
        "enablement_review_only": True,
        "not_runtime_authority": True,
        "source_phase7_12_report_hash": _artifact_hash(phase7_12),
        "source_enablement_guard_valid_fixture_hash": _artifact_hash(valid_fixture),
        "source_enablement_guard_fixture_guard_hash": _artifact_hash(fixture_guard),
        "review_scope": [
            "future_executor_enablement_guard_fixture_review",
            "disabled_executor_flag_review",
            "metadata_only_key_reference_requirement_review",
            "fresh_pre_submit_payload_validation_requirement_review",
            "fresh_pre_order_risk_gate_requirement_review",
            "reconciliation_session_close_requirement_review",
        ],
        "operator_review_checklist": [
            "Confirm Phase 7.12 guard fixture is recorded review-only.",
            "Confirm metadata-only key reference policy remains in force; no key values may be read.",
            "Confirm fresh pre-submit payload validation is required before any later executor stage.",
            "Confirm fresh PreOrderRiskGate recheck is required before any later executor stage.",
            "Confirm manual kill switch and hard caps must be rechecked before any later executor stage.",
            "Confirm reconciliation and session close are required after any future signed testnet session.",
            "Confirm executor/order/runtime flags remain disabled in this review packet.",
        ],
        "metadata_only_key_reference_required": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "hard_caps_rechecked": True,
        "pre_order_risk_gate_rechecked": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "future_executor_enablement_review_required_before_any_order": True,
        "future_executor_enablement_ready_for_operator_review_only": True,
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
    packet["future_executor_enablement_review_packet_sha256"] = sha256_json(packet)
    return packet


def _build_review_guard(*, report_id: str, review_packet: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    validation = validate_enablement_review_packet(review_packet)
    guard_passed = validation.get("packet_valid_review_only") is True
    return {
        "guard_type": "future_signed_testnet_executor_enablement_review_guard_review_only",
        "phase7_13_version": PHASE7_13_VERSION,
        "source_phase7_13_report_id": report_id,
        "review_only": True,
        "enablement_review_guard_only": True,
        "guard_passed": guard_passed,
        "review_packet_validation": validation,
        "phase7_12_guard_fixture_ready": artifacts.get("phase7_12_enablement_guard_fixture_report", {}).get("phase7_12_guard_fixture_ready") is True,
        "source_fixture_guard_passed": artifacts.get("future_executor_enablement_guard_fixture_guard", {}).get("guard_passed") is True,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
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
        "# Phase 7.13 Future Executor Enablement Review Packet — Review Only",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This phase packages Phase 7.12 enablement guard fixture evidence for operator review. It does not enable the executor and does not submit orders.",
        "",
        "## Result",
        "",
        f"- Review packet ready: `{report.get('phase7_13_review_packet_ready')}`",
        f"- Review guard passed: `{report.get('enablement_review_guard_passed')}`",
        f"- Future executor enablement review required before any order: `{report.get('future_executor_enablement_review_required_before_any_order')}`",
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


def build_phase7_13_future_executor_enablement_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_12_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_12_first:
        persist_phase7_12_future_executor_enablement_guard_fixture_report(cfg=cfg)
    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    preliminary_id = stable_id("phase7_13_future_executor_enablement_review_packet", {"source_summary": source_summary, "created_at_utc": created}, 24)
    review_packet = _build_review_packet(report_id=preliminary_id, artifacts=artifacts, created_at_utc=created)
    review_guard = _build_review_guard(report_id=preliminary_id, review_packet=review_packet, artifacts=artifacts, created_at_utc=created)
    phase7_12 = artifacts.get("phase7_12_enablement_guard_fixture_report", {})
    valid_fixture = artifacts.get("future_executor_enablement_guard_valid_fixture", {})
    fixture_guard = artifacts.get("future_executor_enablement_guard_fixture_guard", {})

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_13_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_13_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_12.get("status") != "PHASE7_12_FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_12_ENABLEMENT_GUARD_FIXTURE_NOT_READY")
    if phase7_12.get("phase7_12_guard_fixture_ready") is not True:
        blockers.append("PHASE7_12_GUARD_FIXTURE_READY_FALSE")
    if valid_fixture.get("fixture_type") != "future_signed_testnet_executor_enablement_guard_valid_fixture_review_only":
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_GUARD_VALID_FIXTURE_INVALID")
    if fixture_guard.get("guard_type") != "future_signed_testnet_executor_enablement_guard_fixture_guard_review_only":
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_GUARD_INVALID")
    if fixture_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_GUARD_NOT_PASSED")
    if review_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_REVIEW_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_13_future_executor_enablement_review_packet",
        {"source_summary": source_summary, "review_packet_hash": sha256_json(review_packet), "review_guard_hash": sha256_json(review_guard), "blockers": blockers, "created_at_utc": created},
        24,
    )
    review_packet["source_phase7_13_report_id"] = report_id
    review_guard["source_phase7_13_report_id"] = report_id
    review_packet["future_executor_enablement_review_packet_sha256"] = sha256_json(review_packet)
    review_guard["future_executor_enablement_review_guard_report_sha256"] = sha256_json(review_guard)
    report: dict[str, Any] = {
        "phase7_13_future_executor_enablement_review_packet_id": report_id,
        "phase7_13_version": PHASE7_13_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "review_packet_only": True,
        "phase7_13_review_packet_ready": ready,
        "future_executor_enablement_review_packet_created": True,
        "future_executor_enablement_review_guard_report_created": True,
        "enablement_review_guard_passed": review_guard.get("guard_passed") is True,
        "future_executor_enablement_review_required_before_any_order": True,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_13_allowed_next_scope": "future_executor_enablement_operator_decision_packet_still_disabled" if ready else "resolve_phase7_13_review_packet_blockers",
        "recommended_next_action": "prepare_phase7_14_future_executor_operator_decision_packet_keep_execution_disabled" if ready else "inspect_phase7_13_blockers_and_rerun_phase7_12_phase7_13",
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
    report["future_executor_enablement_review_packet_sha256"] = review_packet["future_executor_enablement_review_packet_sha256"]
    report["future_executor_enablement_review_guard_report_sha256"] = review_guard["future_executor_enablement_review_guard_report_sha256"]
    report["phase7_13_report_sha256"] = sha256_json(report)
    return report, review_packet, review_guard


def persist_phase7_13_future_executor_enablement_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_12_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_13_future_executor_enablement_review_packet")
    report, review_packet, review_guard = build_phase7_13_future_executor_enablement_review_packet_report(cfg=cfg, run_phase7_12_first=run_phase7_12_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_13_future_executor_enablement_review_packet_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_enablement_review_packet_review_only.json", review_packet)
    atomic_write_json(latest / "future_signed_testnet_executor_enablement_review_guard_report.json", review_guard)
    (latest / "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(phase_dir / "phase7_13_future_executor_enablement_review_packet_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_enablement_review_packet_review_only.json", review_packet)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_enablement_review_guard_report.json", review_guard)
    (phase_dir / "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_13_REGISTRY_NAME),
        {
            "phase7_13_future_executor_enablement_review_packet_id": report.get("phase7_13_future_executor_enablement_review_packet_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_13_review_packet_ready": report.get("phase7_13_review_packet_ready"),
            "enablement_review_guard_passed": report.get("enablement_review_guard_passed"),
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
        registry_name=PHASE7_13_REGISTRY_NAME,
        id_field="phase7_13_future_executor_enablement_review_packet_registry_record_id",
        hash_field="phase7_13_future_executor_enablement_review_packet_registry_record_sha256",
        id_prefix="phase7_13_future_executor_enablement_review_packet_registry_record",
    )
    atomic_write_json(latest / "phase7_13_future_executor_enablement_review_packet_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_13_future_executor_enablement_review_packet_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_13_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "validate_enablement_review_packet",
    "build_phase7_13_future_executor_enablement_review_packet_report",
    "persist_phase7_13_future_executor_enablement_review_packet_report",
]
