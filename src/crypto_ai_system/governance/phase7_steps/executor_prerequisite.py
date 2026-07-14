from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.session_operator_handoff import (
    persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report,
)

PHASE7_7_VERSION = "phase7_7_future_executor_review_prerequisite_design_v1"
PHASE7_7_REGISTRY_NAME = "phase7_7_future_executor_review_prerequisite_design_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_BLOCKED_REVIEW_ONLY"

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
    "phase7_6_operator_handoff": "phase7_6_disabled_signed_testnet_session_operator_handoff_report.json",
    "operator_handoff_packet": "disabled_signed_testnet_session_operator_handoff_packet_review_only.json",
    "executor_approval_checklist": "signed_testnet_executor_approval_checklist_review_only.json",
}

PREREQUISITE_ITEMS = [
    "separate_explicit_signed_testnet_executor_approval_packet",
    "fresh_pre_submit_payload_validation_after_future_approval",
    "fresh_pre_order_risk_gate_recheck",
    "manual_kill_switch_confirmation_immediately_before_executor_review",
    "hard_cap_min_max_notional_fee_slippage_confirmation",
    "metadata_only_key_reference_validation_no_key_value_reads",
    "venue_readiness_evidence_review",
    "idempotency_key_policy_review",
    "reconciliation_and_session_close_requirement_review",
    "disabled_executor_flag_review_before_any_future_enablement",
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
        "phase7_7_report_sha256",
        "phase7_6_report_sha256",
        "operator_handoff_packet_sha256",
        "executor_approval_checklist_sha256",
        "future_executor_prerequisite_packet_sha256",
        "future_executor_prerequisite_guard_report_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("checklist_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _checklist_observed(checklist: Mapping[str, Any], item_name: str) -> bool:
    for item in checklist.get("checklist_items") or []:
        if isinstance(item, Mapping) and item.get("item") == item_name:
            return item.get("observed") is True
    return False


def _build_prerequisite_packet(*, report_id: str, phase7_6: Mapping[str, Any], handoff_packet: Mapping[str, Any], checklist: Mapping[str, Any], created_at_utc: str) -> dict[str, Any]:
    prerequisite_checks = [
        {
            "item": "phase7_6_operator_handoff_ready",
            "required": True,
            "observed": phase7_6.get("phase7_6_operator_handoff_ready") is True,
            "blocks_if_false": True,
        },
        {
            "item": "executor_approval_checklist_ready_review_only",
            "required": True,
            "observed": checklist.get("checklist_ready_review_only") is True,
            "blocks_if_false": True,
        },
        {
            "item": "separate_future_executor_approval_required",
            "required": True,
            "observed": _checklist_observed(checklist, "separate_future_executor_approval_required") is True,
            "blocks_if_false": True,
        },
        {
            "item": "no_current_runtime_permission",
            "required": True,
            "observed": handoff_packet.get("operator_next_decision", {}).get("current_packet_grants_runtime_permission") is False,
            "blocks_if_false": True,
        },
        {
            "item": "no_current_order_submission_permission",
            "required": True,
            "observed": handoff_packet.get("operator_next_decision", {}).get("current_packet_grants_order_submission_permission") is False,
            "blocks_if_false": True,
        },
        {
            "item": "metadata_only_key_reference_required",
            "required": True,
            "observed": True,
            "blocks_if_false": True,
        },
        {
            "item": "fresh_pre_submit_validation_required",
            "required": True,
            "observed": True,
            "blocks_if_false": True,
        },
        {
            "item": "fresh_pre_order_risk_gate_recheck_required",
            "required": True,
            "observed": True,
            "blocks_if_false": True,
        },
        {
            "item": "manual_kill_switch_confirmation_required",
            "required": True,
            "observed": True,
            "blocks_if_false": True,
        },
        {
            "item": "reconciliation_session_close_evidence_required",
            "required": True,
            "observed": True,
            "blocks_if_false": True,
        },
    ]
    all_required_observed = all(bool(item["observed"]) for item in prerequisite_checks if item.get("required"))
    return {
        "packet_type": "future_signed_testnet_executor_review_prerequisite_packet_review_only",
        "phase7_7_version": PHASE7_7_VERSION,
        "source_phase7_7_report_id": report_id,
        "source_phase7_6_report_id": phase7_6.get("phase7_6_disabled_signed_testnet_session_operator_handoff_id"),
        "source_operator_handoff_packet_type": handoff_packet.get("packet_type"),
        "source_executor_approval_checklist_type": checklist.get("checklist_type"),
        "review_only": True,
        "prerequisite_design_only": True,
        "future_executor_review_prerequisites_ready_review_only": all_required_observed,
        "executor_enablement_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "allowed_scope": [
            "future_executor_review_prerequisite_design",
            "metadata_only_key_reference_requirement_review",
            "fresh_pre_submit_validation_requirement_review",
            "kill_switch_and_hard_cap_requirement_review",
            "pre_order_risk_gate_requirement_review",
            "reconciliation_session_close_requirement_review",
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
        "prerequisite_checks": prerequisite_checks,
        "required_future_artifacts_before_any_executor_enablement_review": [
            "separate_explicit_signed_testnet_executor_approval_packet",
            "fresh_signed_testnet_pre_submit_payload_validation_report",
            "fresh_pre_order_risk_gate_review_report",
            "metadata_only_key_reference_validation_report",
            "manual_kill_switch_confirmation_report",
            "hard_cap_min_max_notional_fee_slippage_evidence_report",
            "venue_readiness_evidence_report",
            "reconciliation_and_session_close_plan",
        ],
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_prerequisite_guard(*, report_id: str, prerequisite_packet: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    unsafe = _unsafe_flags_by_artifact({"prerequisite_packet": prerequisite_packet, **artifacts})
    checks_ready = prerequisite_packet.get("future_executor_review_prerequisites_ready_review_only") is True
    guard_passed = checks_ready and not unsafe
    return {
        "guard_type": "future_signed_testnet_executor_review_prerequisite_guard_review_only",
        "phase7_7_version": PHASE7_7_VERSION,
        "source_phase7_7_report_id": report_id,
        "review_only": True,
        "guard_passed": guard_passed,
        "future_executor_review_prerequisites_ready_review_only": checks_ready,
        "unsafe_flags_by_artifact": unsafe,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
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
            "# Phase 7.7 Future Executor Review Prerequisite Design — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase designs prerequisites for a possible later signed testnet executor review. It does not enable an executor, submit orders, read secrets, mutate settings, or promote to testnet/live.",
            "",
            "## Result",
            "",
            f"- Prerequisite packet created: `{report.get('future_executor_prerequisite_packet_created')}`",
            f"- Prerequisite guard passed: `{report.get('future_executor_prerequisite_guard_passed')}`",
            f"- Phase 7.7 ready: `{report.get('phase7_7_prerequisite_design_ready')}`",
            "",
            "## Required Future Items Before Any Executor Review",
            "",
            *[f"- `{item}`" for item in PREREQUISITE_ITEMS],
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
            f"`{report.get('phase7_7_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_7_future_executor_review_prerequisite_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_6_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_6_first:
        persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}

    phase7_6 = artifacts.get("phase7_6_operator_handoff", {})
    handoff_packet = artifacts.get("operator_handoff_packet", {})
    checklist = artifacts.get("executor_approval_checklist", {})
    preliminary_id = stable_id("phase7_7_future_executor_review_prerequisite_design", {"source_summary": source_summary, "created_at_utc": created}, 24)
    prerequisite_packet = _build_prerequisite_packet(
        report_id=preliminary_id,
        phase7_6=phase7_6,
        handoff_packet=handoff_packet,
        checklist=checklist,
        created_at_utc=created,
    )
    prerequisite_guard = _build_prerequisite_guard(
        report_id=preliminary_id,
        prerequisite_packet=prerequisite_packet,
        artifacts=artifacts,
        created_at_utc=created,
    )

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_7_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_7_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_6.get("status") != "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_RECORDED_REVIEW_ONLY" or phase7_6.get("phase7_6_operator_handoff_ready") is not True:
        blockers.append("PHASE7_6_OPERATOR_HANDOFF_NOT_READY")
    if phase7_6.get("future_executor_approval_required_before_any_order") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_REQUIREMENT_MISSING")
    if handoff_packet.get("packet_type") != "disabled_signed_testnet_session_operator_handoff_review_only":
        blockers.append("OPERATOR_HANDOFF_PACKET_INVALID")
    if handoff_packet.get("operator_next_decision", {}).get("current_packet_grants_runtime_permission") is not False:
        blockers.append("OPERATOR_HANDOFF_RUNTIME_PERMISSION_NOT_FALSE")
    if handoff_packet.get("operator_next_decision", {}).get("current_packet_grants_order_submission_permission") is not False:
        blockers.append("OPERATOR_HANDOFF_ORDER_PERMISSION_NOT_FALSE")
    if checklist.get("checklist_type") != "signed_testnet_executor_approval_checklist_review_only":
        blockers.append("EXECUTOR_APPROVAL_CHECKLIST_INVALID")
    if checklist.get("checklist_ready_review_only") is not True:
        blockers.append("EXECUTOR_APPROVAL_CHECKLIST_NOT_READY")
    if prerequisite_packet.get("future_executor_review_prerequisites_ready_review_only") is not True:
        blockers.append("FUTURE_EXECUTOR_REVIEW_PREREQUISITES_NOT_READY")
    if prerequisite_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_REVIEW_PREREQUISITE_GUARD_NOT_PASSED")
    for generated_name, generated in {"prerequisite_packet": prerequisite_packet, "prerequisite_guard": prerequisite_guard}.items():
        flags = _unsafe_fields(generated)
        if flags:
            blockers.append(f"UNSAFE_PHASE7_7_GENERATED_ARTIFACT_FLAGS:{generated_name}:{','.join(flags)}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_7_future_executor_review_prerequisite_design",
        {
            "source_summary": source_summary,
            "prerequisite_packet_hash": sha256_json(prerequisite_packet),
            "prerequisite_guard_hash": sha256_json(prerequisite_guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    prerequisite_packet = {**prerequisite_packet, "source_phase7_7_report_id": report_id}
    prerequisite_guard = {**prerequisite_guard, "source_phase7_7_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_7_future_executor_review_prerequisite_design_id": report_id,
        "phase7_7_version": PHASE7_7_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "prerequisite_design_only": True,
        "phase7_7_prerequisite_design_ready": ready,
        "future_executor_prerequisite_packet_created": True,
        "future_executor_prerequisite_guard_created": True,
        "future_executor_prerequisite_guard_passed": prerequisite_guard.get("guard_passed") is True,
        "future_executor_review_prerequisites_ready_review_only": prerequisite_packet.get("future_executor_review_prerequisites_ready_review_only") is True,
        "phase7_6_operator_handoff_ready": phase7_6.get("phase7_6_operator_handoff_ready") is True,
        "executor_approval_checklist_ready_review_only": checklist.get("checklist_ready_review_only") is True,
        "metadata_only_key_reference_required": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "hard_cap_min_max_notional_fee_slippage_confirmation_required": True,
        "venue_readiness_evidence_required": True,
        "reconciliation_session_close_requirement_required": True,
        "future_executor_review_required_before_any_order": True,
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
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_7_allowed_next_scope": "future_executor_approval_packet_template_still_disabled" if ready else "resolve_phase7_7_prerequisite_design_blockers",
        "recommended_next_action": "prepare_phase7_8_future_executor_approval_packet_template_keep_execution_disabled" if ready else "inspect_phase7_7_blockers_and_rerun_phase7_6_phase7_7",
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
    report["future_executor_prerequisite_packet_sha256"] = sha256_json(prerequisite_packet)
    report["future_executor_prerequisite_guard_report_sha256"] = sha256_json(prerequisite_guard)
    report["phase7_7_report_sha256"] = sha256_json(report)
    return report, prerequisite_packet, prerequisite_guard


def persist_phase7_7_future_executor_review_prerequisite_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_6_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_7_future_executor_review_prerequisite_design")
    report, prerequisite_packet, prerequisite_guard = build_phase7_7_future_executor_review_prerequisite_design_report(cfg=cfg, run_phase7_6_first=run_phase7_6_first)
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase7_7_future_executor_review_prerequisite_design_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_review_prerequisite_packet_review_only.json", prerequisite_packet)
    atomic_write_json(latest / "future_signed_testnet_executor_review_prerequisite_guard_report.json", prerequisite_guard)
    (latest / "PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase7_7_future_executor_review_prerequisite_design_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_review_prerequisite_packet_review_only.json", prerequisite_packet)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_review_prerequisite_guard_report.json", prerequisite_guard)
    (phase_dir / "PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_7_REGISTRY_NAME),
        {
            "phase7_7_future_executor_review_prerequisite_design_id": report.get("phase7_7_future_executor_review_prerequisite_design_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_7_prerequisite_design_ready": report.get("phase7_7_prerequisite_design_ready"),
            "future_executor_review_prerequisites_ready_review_only": report.get("future_executor_review_prerequisites_ready_review_only"),
            "future_executor_prerequisite_guard_passed": report.get("future_executor_prerequisite_guard_passed"),
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
        registry_name=PHASE7_7_REGISTRY_NAME,
        id_field="phase7_7_future_executor_review_prerequisite_design_registry_record_id",
        hash_field="phase7_7_future_executor_review_prerequisite_design_registry_record_sha256",
        id_prefix="phase7_7_future_executor_review_prerequisite_design_registry_record",
    )
    atomic_write_json(latest / "phase7_7_future_executor_review_prerequisite_design_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_7_future_executor_review_prerequisite_design_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_7_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_7_future_executor_review_prerequisite_design_report",
    "persist_phase7_7_future_executor_review_prerequisite_design_report",
]
