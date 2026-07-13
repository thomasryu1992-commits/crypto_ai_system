from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.readiness_common import (
    manual_file_summary as _actual_file_summary,
    artifact_hash as _artifact_hash,
    latest_dir as _latest_dir,
    manual_value_filled as _manual_value_filled,
    positive_integer as _positive_int,
    positive_number as _positive_number,
    read_latest_json as _read_latest_json,
    read_optional_json as _read_optional_json,
    bool_value as _safe_bool,
    source_summary as _source_summary,
    storage_dir as _storage_dir,
    unsafe_fields as _unsafe_fields,
    unsafe_flags_by_artifact as _unsafe_flags_by_artifact,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE6_6_VERSION = "phase6_6_actual_intake_validation_bridge_v1"
PHASE6_6_REGISTRY_NAME = "phase6_6_actual_intake_validation_bridge_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_BLOCKED_REVIEW_ONLY"

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
    "phase6_3_signed_testnet_readiness_gate_review": "phase6_3_signed_testnet_readiness_gate_review_report.json",
    "phase6_4_signed_testnet_readiness_review_packet": "phase6_4_signed_testnet_readiness_review_packet_report.json",
    "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox": "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report.json",
}


def _validate_actual_intake_payloads(approval: Mapping[str, Any], unlock: Mapping[str, Any]) -> dict[str, Any]:
    approval_data = dict(approval or {})
    unlock_data = dict(unlock or {})
    findings: dict[str, Any] = {}
    blockers: list[str] = []

    approval_required = [
        "approval_packet_id",
        "approval_intake_id",
        "approver_info",
        "ticket_or_signature",
        "source_report_hash",
        "approval_packet_hash",
        "feature_matrix_hash",
        "profile_candidate_hash",
        "canonical_utc_timestamp",
    ]
    unlock_required = [
        "operator_id",
        "operator_ticket_or_signature",
        "canonical_utc_timestamp",
        "approval_intake_id",
        "approval_packet_id",
        "max_testnet_notional_usd",
        "max_testnet_order_count",
        "max_testnet_daily_loss_usd",
        "kill_switch_rechecked",
        "hard_caps_rechecked",
        "pre_order_risk_gate_rechecked",
    ]

    missing_approval = [field for field in approval_required if not _manual_value_filled(approval_data.get(field))]
    missing_unlock = [field for field in unlock_required if not _manual_value_filled(unlock_data.get(field))]
    if missing_approval:
        blockers.append("ACTUAL_APPROVAL_REQUIRED_FIELDS_MISSING_OR_PLACEHOLDER:" + ",".join(missing_approval))
    if missing_unlock:
        blockers.append("ACTUAL_OPERATOR_REQUIRED_FIELDS_MISSING_OR_PLACEHOLDER:" + ",".join(missing_unlock))

    approval_packet_match = approval_data.get("approval_packet_id") == unlock_data.get("approval_packet_id")
    approval_intake_match = approval_data.get("approval_intake_id") == unlock_data.get("approval_intake_id")
    if not approval_packet_match:
        blockers.append("APPROVAL_PACKET_ID_MISMATCH_BETWEEN_APPROVAL_AND_OPERATOR_REQUEST")
    if not approval_intake_match:
        blockers.append("APPROVAL_INTAKE_ID_MISMATCH_BETWEEN_APPROVAL_AND_OPERATOR_REQUEST")

    if not _positive_number(unlock_data.get("max_testnet_notional_usd")):
        blockers.append("MAX_TESTNET_NOTIONAL_USD_NOT_POSITIVE_NUMERIC")
    if not _positive_int(unlock_data.get("max_testnet_order_count")):
        blockers.append("MAX_TESTNET_ORDER_COUNT_NOT_POSITIVE_INTEGER")
    if not _positive_number(unlock_data.get("max_testnet_daily_loss_usd")):
        blockers.append("MAX_TESTNET_DAILY_LOSS_USD_NOT_POSITIVE_NUMERIC")
    for field in ("kill_switch_rechecked", "hard_caps_rechecked", "pre_order_risk_gate_rechecked"):
        if unlock_data.get(field) is not True:
            blockers.append(f"{field.upper()}_NOT_TRUE")

    approval_unsafe = _unsafe_fields(approval_data)
    unlock_unsafe = _unsafe_fields(unlock_data)
    if approval_unsafe:
        blockers.append("UNSAFE_ACTUAL_APPROVAL_FLAG:" + ",".join(approval_unsafe))
    if unlock_unsafe:
        blockers.append("UNSAFE_ACTUAL_OPERATOR_UNLOCK_FLAG:" + ",".join(unlock_unsafe))

    findings.update(
        {
            "approval_required_fields_present": not missing_approval,
            "operator_required_fields_present": not missing_unlock,
            "approval_packet_id_match": approval_packet_match,
            "approval_intake_id_match": approval_intake_match,
            "hard_caps_numeric": _positive_number(unlock_data.get("max_testnet_notional_usd")) and _positive_int(unlock_data.get("max_testnet_order_count")) and _positive_number(unlock_data.get("max_testnet_daily_loss_usd")),
            "kill_switch_rechecked": unlock_data.get("kill_switch_rechecked") is True,
            "hard_caps_rechecked": unlock_data.get("hard_caps_rechecked") is True,
            "pre_order_risk_gate_rechecked": unlock_data.get("pre_order_risk_gate_rechecked") is True,
            "approval_unsafe_truthy_fields": approval_unsafe,
            "operator_unsafe_truthy_fields": unlock_unsafe,
            "validation_blockers": sorted(dict.fromkeys(blockers)),
        }
    )
    return findings


def _build_phase7_review_packet(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet_type": "phase7_entry_review_packet_review_only",
        "source_phase6_6_bridge_id": report.get("phase6_6_actual_intake_validation_bridge_id"),
        "phase7_entry_review_possible": report.get("phase7_entry_review_possible"),
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_validation_design_only": True,
        "bridge_status": report.get("status"),
        "bridge_block_reasons": report.get("block_reasons"),
        "actual_manual_approval_submission_sha256": (report.get("actual_manual_approval_submission_summary") or {}).get("sha256"),
        "actual_operator_unlock_request_sha256": (report.get("actual_operator_unlock_request_summary") or {}).get("sha256"),
        "source_evidence_hash_summary": report.get("source_evidence_hash_summary"),
        "required_next_review_steps": [
            "Design Phase 7 as signed testnet validation only.",
            "Keep ready_for_signed_testnet_execution=false until a separate executor approval stage exists.",
            "Keep testnet_order_submission_allowed=false in this bridge packet.",
            "Do not read API key values or secret files.",
            "Re-run PreOrderRiskGate immediately before any later signed testnet executor enablement review.",
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
        "created_at_utc": report.get("created_at_utc"),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return f"""# Phase 6.6 Actual Intake Validation Bridge — Review Only

Status: `{report.get('status')}`

This bridge inspects the actual manual approval submission and actual operator unlock request detected by Phase 6.5. It may create a Phase 7 entry review packet, but it does not enable signed testnet execution, does not enable order submission, and does not grant runtime authority.

## Bridge Result

- Phase 7 entry review possible: `{report.get('phase7_entry_review_possible')}`
- Phase 7 execution authority: `{report.get('phase7_execution_authority')}`
- Phase 7 order submission authority: `{report.get('phase7_order_submission_authority')}`
- Ready for signed testnet execution: `{report.get('ready_for_signed_testnet_execution')}`
- Testnet order submission allowed: `{report.get('testnet_order_submission_allowed')}`

## Blockers

{blocker_lines}

## Safety Invariants

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`
- `runtime_settings_mutated=false`
- `score_weights_mutated=false`
- `auto_promotion_allowed=false`

## Operator Note

Phase 6.6 is a bridge into Phase 7 design/review only. It is not a signed testnet executor and must not submit orders.
"""


def build_phase6_6_actual_intake_validation_bridge_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    created = utc_now_canonical()

    artifacts = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing_artifacts = [name for name, payload in artifacts.items() if not payload]
    unsafe_flags = _unsafe_flags_by_artifact(artifacts)
    phase5 = artifacts.get("phase5_manual_approval_intake_validation", {})
    phase6_5 = artifacts.get("phase6_5_actual_manual_approval_operator_unlock_intake_sandbox", {})

    actual_approval_path = cfg.root / "storage" / "manual_approval" / "approval_intake_submission.json"
    actual_unlock_latest_path = latest / "operator_unlock_request.json"
    actual_unlock_archive_path = cfg.root / "storage" / "signed_testnet" / "operator_unlock_request.json"
    actual_approval_payload = _read_optional_json(actual_approval_path) if actual_approval_path.exists() else {}
    actual_unlock_path = actual_unlock_latest_path if actual_unlock_latest_path.exists() else actual_unlock_archive_path
    actual_unlock_payload = _read_optional_json(actual_unlock_path) if actual_unlock_path.exists() else {}
    actual_approval_summary = _actual_file_summary(actual_approval_path)
    actual_unlock_summary = _actual_file_summary(actual_unlock_path)

    payload_validation = _validate_actual_intake_payloads(actual_approval_payload, actual_unlock_payload)
    blockers: list[str] = []
    if not actual_approval_path.exists():
        blockers.append("ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING")
    if not actual_unlock_payload:
        blockers.append("ACTUAL_OPERATOR_UNLOCK_REQUEST_MISSING")
    blockers.extend([f"MISSING_BRIDGE_SOURCE_ARTIFACT:{name}" for name in missing_artifacts])
    if unsafe_flags:
        blockers.extend([f"UNSAFE_BRIDGE_SOURCE_FLAG:{name}:{','.join(flags)}" for name, flags in unsafe_flags.items()])
    blockers.extend(payload_validation.get("validation_blockers") or [])

    phase5_review_valid = (
        phase5.get("manual_approval_submission_present") is True
        and phase5.get("manual_approval_submission_hash_chain_matches_draft") is True
        and phase5.get("approval_intake_submitted") is True
        and phase5.get("status") == "PHASE5_MANUAL_APPROVAL_INTAKE_VALIDATION_RECORDED_REVIEW_ONLY"
    )
    if not phase5_review_valid:
        blockers.append("PHASE5_ACTUAL_APPROVAL_REVIEW_ONLY_VALIDATION_NOT_READY")

    phase6_5_actual_detected = (
        phase6_5.get("actual_manual_approval_submission_present") is True
        and phase6_5.get("actual_operator_unlock_request_present") is True
        and phase6_5.get("status") == "PHASE6_5_ACTUAL_APPROVAL_OPERATOR_UNLOCK_INTAKE_SANDBOX_RECORDED_REVIEW_ONLY"
    )
    if not phase6_5_actual_detected:
        blockers.append("PHASE6_5_ACTUAL_INTAKE_SANDBOX_NOT_READY")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    bridge_conditions_met = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if bridge_conditions_met else STATUS_BLOCKED_REVIEW_ONLY
    bridge_id = stable_id(
        "phase6_6_actual_intake_validation_bridge",
        {
            "source_hashes": {name: _artifact_hash(payload) for name, payload in artifacts.items()},
            "actual_approval_sha256": actual_approval_summary.get("sha256"),
            "actual_unlock_sha256": actual_unlock_summary.get("sha256"),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase6_6_actual_intake_validation_bridge_id": bridge_id,
        "phase6_6_version": PHASE6_6_VERSION,
        "status": status,
        "blocked": not bridge_conditions_met,
        "fail_closed": not bridge_conditions_met,
        "review_only": True,
        "bridge_only": True,
        "actual_intake_files_created_by_this_module": False,
        "actual_manual_approval_submission_present": actual_approval_path.exists(),
        "actual_operator_unlock_request_present": bool(actual_unlock_payload),
        "actual_manual_approval_submission_summary": actual_approval_summary,
        "actual_operator_unlock_request_summary": actual_unlock_summary,
        "payload_validation": payload_validation,
        "phase5_review_only_validation_ready": phase5_review_valid,
        "phase6_5_actual_intake_sandbox_ready": phase6_5_actual_detected,
        "missing_source_artifacts": missing_artifacts,
        "unsafe_flags_by_artifact": unsafe_flags,
        "source_evidence_hash_summary": {name: _source_summary(name, payload) for name, payload in artifacts.items()},
        "block_reasons": blockers,
        "phase7_entry_review_packet_created": True,
        "phase7_entry_review_possible": bridge_conditions_met,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_validation_design_only": True,
        "phase7_allowed_next_scope": "signed_testnet_validation_design_review_only" if bridge_conditions_met else "resolve_bridge_blockers",
        "recommended_next_action": "draft_phase7_signed_testnet_validation_design_keep_executor_disabled" if bridge_conditions_met else "resolve_actual_intake_bridge_blockers_and_rerun_phase5_phase6_5_phase6_6",
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
        "created_at_utc": created,
    }
    report["phase7_entry_review_packet_sha256"] = sha256_json(_build_phase7_review_packet(report))
    report["phase6_6_report_sha256"] = sha256_json(report)
    return report


def persist_phase6_6_actual_intake_validation_bridge_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase6_6_actual_intake_validation_bridge")
    report = build_phase6_6_actual_intake_validation_bridge_report(cfg=cfg)
    phase7_packet = _build_phase7_review_packet(report)
    markdown = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase6_6_actual_intake_validation_bridge_report.json", report)
    atomic_write_json(latest / "phase7_entry_review_packet_review_only.json", phase7_packet)
    (latest / "PHASE7_ENTRY_REVIEW_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")
    atomic_write_json(phase_dir / "phase6_6_actual_intake_validation_bridge_report.json", report)
    atomic_write_json(phase_dir / "phase7_entry_review_packet_review_only.json", phase7_packet)
    (phase_dir / "PHASE7_ENTRY_REVIEW_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE6_6_REGISTRY_NAME),
        {
            "phase6_6_actual_intake_validation_bridge_id": report.get("phase6_6_actual_intake_validation_bridge_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_entry_review_possible": report.get("phase7_entry_review_possible"),
            "phase7_execution_authority": False,
            "phase7_order_submission_authority": False,
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
        registry_name=PHASE6_6_REGISTRY_NAME,
        id_field="phase6_6_actual_intake_validation_bridge_registry_record_id",
        hash_field="phase6_6_actual_intake_validation_bridge_registry_record_sha256",
        id_prefix="phase6_6_actual_intake_validation_bridge_registry_record",
    )
    atomic_write_json(latest / "phase6_6_actual_intake_validation_bridge_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase6_6_actual_intake_validation_bridge_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE6_6_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase6_6_actual_intake_validation_bridge_report",
    "persist_phase6_6_actual_intake_validation_bridge_report",
]
