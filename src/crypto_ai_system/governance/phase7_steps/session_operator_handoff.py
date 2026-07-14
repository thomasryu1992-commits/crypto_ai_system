from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.session_close_review import (
    persist_phase7_5_reconciliation_session_close_review_packet_report,
)

PHASE7_6_VERSION = "phase7_6_disabled_signed_testnet_session_operator_handoff_v1"
PHASE7_6_REGISTRY_NAME = "phase7_6_disabled_signed_testnet_session_operator_handoff_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_BLOCKED_REVIEW_ONLY"

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
    "phase7_5_reconciliation_session_close_review_packet": "phase7_5_reconciliation_session_close_review_packet_report.json",
    "reconciliation_session_close_review_packet": "signed_testnet_reconciliation_session_close_review_packet_review_only.json",
    "reconciliation_session_close_promotion_guard": "signed_testnet_reconciliation_session_close_promotion_guard_report.json",
}


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
        "phase7_6_report_sha256",
        "phase7_5_report_sha256",
        "reconciliation_session_close_review_packet_sha256",
        "promotion_guard_report_sha256",
        "operator_handoff_packet_sha256",
        "executor_approval_checklist_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("report_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _build_executor_approval_checklist(*, report_id: str, phase7_5: Mapping[str, Any], created_at_utc: str) -> dict[str, Any]:
    checklist_items = [
        {
            "item": "phase7_5_review_packet_confirmed",
            "required": True,
            "observed": phase7_5.get("phase7_5_review_packet_ready") is True,
            "blocks_if_false": True,
        },
        {
            "item": "promotion_guard_confirmed",
            "required": True,
            "observed": phase7_5.get("promotion_guard_passed") is True,
            "blocks_if_false": True,
        },
        {
            "item": "disabled_reconciliation_confirmed",
            "required": True,
            "observed": phase7_5.get("disabled_execution_reconciled_review_only") is True,
            "blocks_if_false": True,
        },
        {
            "item": "session_close_confirmed",
            "required": True,
            "observed": phase7_5.get("session_closed_review_only") is True,
            "blocks_if_false": True,
        },
        {
            "item": "no_reconciliation_mismatch",
            "required": True,
            "observed": phase7_5.get("reconciliation_mismatch") is False,
            "blocks_if_false": True,
        },
        {
            "item": "no_actual_order_submission",
            "required": True,
            "observed": phase7_5.get("external_order_submission_performed") is False and phase7_5.get("actual_order_submission_performed") is False,
            "blocks_if_false": True,
        },
        {
            "item": "executor_remains_disabled",
            "required": True,
            "observed": phase7_5.get("signed_order_executor_enabled") is False,
            "blocks_if_false": True,
        },
        {
            "item": "separate_future_executor_approval_required",
            "required": True,
            "observed": True,
            "blocks_if_false": True,
        },
    ]
    all_required_observed = all(bool(item["observed"]) for item in checklist_items if item.get("required"))
    return {
        "checklist_type": "signed_testnet_executor_approval_checklist_review_only",
        "phase7_6_version": PHASE7_6_VERSION,
        "source_phase7_6_report_id": report_id,
        "review_only": True,
        "checklist_ready_review_only": all_required_observed,
        "all_required_items_observed": all_required_observed,
        "executor_approval_authority": False,
        "executor_enablement_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "checklist_items": checklist_items,
        "required_future_operator_actions_before_any_executor_review": [
            "Create a separate explicit signed testnet executor approval packet.",
            "Re-run fresh pre-submit payload validation after any future approval.",
            "Confirm metadata-only key reference validation without key value reads.",
            "Confirm manual kill switch immediately before any future executor review.",
            "Confirm hard caps, min/max notional, fee/slippage evidence, and venue readiness.",
            "Confirm reconciliation and session close requirements before and after any future testnet session.",
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


def _build_operator_handoff_packet(
    *, report_id: str, phase7_5: Mapping[str, Any], review_packet: Mapping[str, Any], promotion_guard: Mapping[str, Any], checklist: Mapping[str, Any], created_at_utc: str
) -> dict[str, Any]:
    return {
        "packet_type": "disabled_signed_testnet_session_operator_handoff_review_only",
        "phase7_6_version": PHASE7_6_VERSION,
        "source_phase7_6_report_id": report_id,
        "source_phase7_5_report_id": phase7_5.get("phase7_5_reconciliation_session_close_review_packet_id"),
        "source_reconciliation_session_close_review_packet_type": review_packet.get("packet_type"),
        "source_promotion_guard_type": promotion_guard.get("guard_type"),
        "source_executor_approval_checklist_type": checklist.get("checklist_type"),
        "review_only": True,
        "operator_handoff_only": True,
        "actual_executor_enablement_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "allowed_scope": [
            "operator_review_of_disabled_session_evidence",
            "executor_approval_checklist_review",
            "future_executor_review_preparation",
            "fail_closed_blocker_resolution",
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
        "operator_summary": {
            "phase7_5_review_packet_ready": phase7_5.get("phase7_5_review_packet_ready") is True,
            "promotion_guard_passed": phase7_5.get("promotion_guard_passed") is True,
            "disabled_execution_reconciled_review_only": phase7_5.get("disabled_execution_reconciled_review_only") is True,
            "session_closed_review_only": phase7_5.get("session_closed_review_only") is True,
            "reconciliation_mismatch": phase7_5.get("reconciliation_mismatch") is True,
            "observed_fill_count": phase7_5.get("observed_fill_count"),
            "observed_position_delta": phase7_5.get("observed_position_delta"),
            "observed_balance_delta": phase7_5.get("observed_balance_delta"),
        },
        "operator_next_decision": {
            "current_decision_scope": "review_disabled_session_evidence_only",
            "future_executor_approval_required_before_any_order": True,
            "current_packet_grants_runtime_permission": False,
            "current_packet_grants_order_submission_permission": False,
        },
        "executor_approval_checklist_ready_review_only": checklist.get("checklist_ready_review_only") is True,
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


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 7.6 Disabled Signed Testnet Session Operator Handoff — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase packages Phase 7.5 reconciliation/session-close review evidence into an operator handoff packet. It does not enable a signed testnet executor, submit orders, read secrets, mutate settings, or promote to testnet/live.",
            "",
            "## Result",
            "",
            f"- Operator handoff packet created: `{report.get('operator_handoff_packet_created')}`",
            f"- Executor approval checklist created: `{report.get('executor_approval_checklist_created')}`",
            f"- Phase 7.6 handoff ready: `{report.get('phase7_6_operator_handoff_ready')}`",
            f"- Promotion guard passed: `{report.get('promotion_guard_passed')}`",
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
            f"`{report.get('phase7_6_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_6_disabled_signed_testnet_session_operator_handoff_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_5_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_5_first:
        persist_phase7_5_reconciliation_session_close_review_packet_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}

    phase7_5 = artifacts.get("phase7_5_reconciliation_session_close_review_packet", {})
    review_packet = artifacts.get("reconciliation_session_close_review_packet", {})
    promotion_guard = artifacts.get("reconciliation_session_close_promotion_guard", {})
    preliminary_id = stable_id("phase7_6_disabled_signed_testnet_session_operator_handoff", {"source_summary": source_summary, "created_at_utc": created}, 24)
    checklist = _build_executor_approval_checklist(report_id=preliminary_id, phase7_5=phase7_5, created_at_utc=created)
    handoff_packet = _build_operator_handoff_packet(
        report_id=preliminary_id,
        phase7_5=phase7_5,
        review_packet=review_packet,
        promotion_guard=promotion_guard,
        checklist=checklist,
        created_at_utc=created,
    )

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_6_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_6_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_5.get("status") != "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_RECORDED_REVIEW_ONLY" or phase7_5.get("phase7_5_review_packet_ready") is not True:
        blockers.append("PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_NOT_READY")
    if phase7_5.get("promotion_guard_passed") is not True:
        blockers.append("PHASE7_5_PROMOTION_GUARD_NOT_PASSED")
    if phase7_5.get("reconciliation_mismatch") is not False:
        blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    if review_packet.get("packet_type") != "signed_testnet_reconciliation_session_close_review_packet_review_only":
        blockers.append("RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_INVALID")
    if promotion_guard.get("guard_type") != "signed_testnet_reconciliation_session_close_promotion_guard_review_only":
        blockers.append("RECONCILIATION_SESSION_CLOSE_PROMOTION_GUARD_INVALID")
    if promotion_guard.get("guard_passed") is not True:
        blockers.append("RECONCILIATION_SESSION_CLOSE_PROMOTION_GUARD_NOT_PASSED")
    if checklist.get("checklist_ready_review_only") is not True:
        blockers.append("EXECUTOR_APPROVAL_CHECKLIST_NOT_READY")
    for generated_name, generated in {"operator_handoff_packet": handoff_packet, "executor_approval_checklist": checklist}.items():
        flags = _unsafe_fields(generated)
        if flags:
            blockers.append(f"UNSAFE_PHASE7_6_GENERATED_ARTIFACT_FLAGS:{generated_name}:{','.join(flags)}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_6_disabled_signed_testnet_session_operator_handoff",
        {
            "source_summary": source_summary,
            "checklist_hash": sha256_json(checklist),
            "handoff_packet_hash": sha256_json(handoff_packet),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    checklist = {**checklist, "source_phase7_6_report_id": report_id}
    handoff_packet = {**handoff_packet, "source_phase7_6_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_6_disabled_signed_testnet_session_operator_handoff_id": report_id,
        "phase7_6_version": PHASE7_6_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "operator_handoff_only": True,
        "phase7_6_operator_handoff_ready": ready,
        "operator_handoff_packet_created": True,
        "executor_approval_checklist_created": True,
        "executor_approval_checklist_ready_review_only": checklist.get("checklist_ready_review_only") is True,
        "phase7_5_review_packet_ready": phase7_5.get("phase7_5_review_packet_ready") is True,
        "promotion_guard_passed": phase7_5.get("promotion_guard_passed") is True and promotion_guard.get("guard_passed") is True,
        "disabled_execution_reconciled_review_only": phase7_5.get("disabled_execution_reconciled_review_only") is True,
        "session_closed_review_only": phase7_5.get("session_closed_review_only") is True,
        "reconciliation_mismatch": phase7_5.get("reconciliation_mismatch") is True,
        "observed_fill_count": phase7_5.get("observed_fill_count"),
        "observed_position_delta": phase7_5.get("observed_position_delta"),
        "observed_balance_delta": phase7_5.get("observed_balance_delta"),
        "future_executor_approval_required_before_any_order": True,
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
        "phase7_6_allowed_next_scope": "future_executor_review_prerequisite_design_still_disabled" if ready else "resolve_phase7_6_operator_handoff_blockers",
        "recommended_next_action": "prepare_phase7_7_executor_prerequisite_design_keep_execution_disabled" if ready else "inspect_phase7_6_blockers_and_rerun_phase7_5_phase7_6",
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
    report["operator_handoff_packet_sha256"] = sha256_json(handoff_packet)
    report["executor_approval_checklist_sha256"] = sha256_json(checklist)
    report["phase7_6_report_sha256"] = sha256_json(report)
    return report, handoff_packet, checklist


def persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_5_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_6_disabled_signed_testnet_session_operator_handoff")
    report, handoff_packet, checklist = build_phase7_6_disabled_signed_testnet_session_operator_handoff_report(cfg=cfg, run_phase7_5_first=run_phase7_5_first)
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase7_6_disabled_signed_testnet_session_operator_handoff_report.json", report)
    atomic_write_json(latest / "disabled_signed_testnet_session_operator_handoff_packet_review_only.json", handoff_packet)
    atomic_write_json(latest / "signed_testnet_executor_approval_checklist_review_only.json", checklist)
    (latest / "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase7_6_disabled_signed_testnet_session_operator_handoff_report.json", report)
    atomic_write_json(phase_dir / "disabled_signed_testnet_session_operator_handoff_packet_review_only.json", handoff_packet)
    atomic_write_json(phase_dir / "signed_testnet_executor_approval_checklist_review_only.json", checklist)
    (phase_dir / "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_6_REGISTRY_NAME),
        {
            "phase7_6_disabled_signed_testnet_session_operator_handoff_id": report.get("phase7_6_disabled_signed_testnet_session_operator_handoff_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_6_operator_handoff_ready": report.get("phase7_6_operator_handoff_ready"),
            "executor_approval_checklist_ready_review_only": report.get("executor_approval_checklist_ready_review_only"),
            "promotion_guard_passed": report.get("promotion_guard_passed"),
            "future_executor_approval_required_before_any_order": True,
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
        registry_name=PHASE7_6_REGISTRY_NAME,
        id_field="phase7_6_disabled_signed_testnet_session_operator_handoff_registry_record_id",
        hash_field="phase7_6_disabled_signed_testnet_session_operator_handoff_registry_record_sha256",
        id_prefix="phase7_6_disabled_signed_testnet_session_operator_handoff_registry_record",
    )
    atomic_write_json(latest / "phase7_6_disabled_signed_testnet_session_operator_handoff_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_6_disabled_signed_testnet_session_operator_handoff_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_6_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_6_disabled_signed_testnet_session_operator_handoff_report",
    "persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report",
]
