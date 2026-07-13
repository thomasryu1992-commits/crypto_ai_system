from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.readiness_common import (
    artifact_hash as _artifact_hash,
    latest_dir as _latest_dir,
    manual_file_summary as _manual_file_summary,
    read_latest_json as _read_latest_json,
    read_optional_json as _read_optional_json,
    bool_value as _safe_bool,
    source_summary as _source_summary,
    storage_dir as _storage_dir,
    unsafe_flags_by_artifact as _unsafe_flags_by_artifact,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE6_5_VERSION = "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_v1"
PHASE6_5_REGISTRY_NAME = "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE6_5_ACTUAL_APPROVAL_OPERATOR_UNLOCK_INTAKE_SANDBOX_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE6_5_ACTUAL_APPROVAL_OPERATOR_UNLOCK_INTAKE_SANDBOX_BLOCKED_REVIEW_ONLY"

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
    "phase5_1_manual_approval_operator_handoff": "phase5_1_manual_approval_operator_handoff_report.json",
    "phase5_2_manual_approval_submission_fixture_validator": "phase5_2_manual_approval_submission_fixture_validator_report.json",
    "phase6_signed_testnet_preparation_preview": "phase6_signed_testnet_preparation_preview_report.json",
    "phase6_1_operator_unlock_request_template": "phase6_1_signed_testnet_operator_unlock_request_template_report.json",
    "phase6_2_operator_unlock_request_fixture_validator": "phase6_2_operator_unlock_request_fixture_validator_report.json",
    "phase6_3_signed_testnet_readiness_gate_review": "phase6_3_signed_testnet_readiness_gate_review_report.json",
    "phase6_4_signed_testnet_readiness_review_packet": "phase6_4_signed_testnet_readiness_review_packet_report.json",
}


def _build_sandbox_sequence() -> list[dict[str, Any]]:
    return [
        {
            "sequence": 1,
            "step": "detect_actual_manual_approval_submission",
            "required_input": "storage/manual_approval/approval_intake_submission.json",
            "fail_closed_if_missing": True,
        },
        {
            "sequence": 2,
            "step": "detect_actual_operator_unlock_request",
            "required_input": "storage/latest/operator_unlock_request.json or storage/signed_testnet/operator_unlock_request.json",
            "fail_closed_if_missing": True,
        },
        {
            "sequence": 3,
            "step": "hash_chain_precheck",
            "required_input": "Phase 4.4 approval draft, Phase 5 intake, Phase 6.1 template, Phase 6.4 readiness packet",
            "fail_closed_if_mismatch": True,
        },
        {
            "sequence": 4,
            "step": "rerun_phase5_manual_approval_intake_validation",
            "required_result": "phase5 status recorded review-only with approval_intake_submitted=true but still not runtime authority",
            "fail_closed_if_not_validated": True,
        },
        {
            "sequence": 5,
            "step": "rerun_phase6_3_signed_testnet_readiness_gate_review",
            "required_result": "all blockers cleared except execution flags remain disabled until a later explicitly approved executor stage",
            "fail_closed_if_blocked": True,
        },
        {
            "sequence": 6,
            "step": "phase7_entry_review_only_decision",
            "required_result": "Phase 7 may be designed only as signed testnet validation; this sandbox never submits orders",
            "fail_closed_if_any_unsafe_flag_true": True,
        },
    ]


def _build_operator_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    sequence = report.get("sandbox_validation_sequence") or []
    sequence_lines = "\n".join(
        f"- {item.get('sequence')}. `{item.get('step')}` — required: `{item.get('required_input') or item.get('required_result')}`"
        for item in sequence
    )
    return f"""# Phase 6.5 Actual Manual Approval / Operator Unlock Intake Sandbox — Review Only

Status: `{report.get('status')}`

This sandbox defines how actual manual approval and operator unlock artifacts would be detected and reviewed before any later Phase 7 signed testnet validation design. It does not create `approval_intake_submission.json`, does not create `operator_unlock_request.json`, does not enable the signed executor, and does not submit orders.

## Current Sandbox Result

- Actual manual approval submission present: `{report.get('actual_manual_approval_submission_present')}`
- Actual operator unlock request present: `{report.get('actual_operator_unlock_request_present')}`
- Sandbox intake ready for Phase 7 review: `{report.get('phase7_entry_review_possible')}`
- Ready for signed testnet execution: `{report.get('ready_for_signed_testnet_execution')}`
- Testnet order submission allowed: `{report.get('testnet_order_submission_allowed')}`

## Blockers

{blocker_lines}

## Review Sequence

{sequence_lines}

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

When a human intentionally creates the real manual approval submission and real operator unlock request, rerun Phase 5, Phase 6.3, Phase 6.4, and this Phase 6.5 sandbox. Any missing file, hash mismatch, unsafe flag, missing hard cap, or unrechecked kill switch must keep Phase 7 blocked.
"""


def build_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report(
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

    actual_approval_path = cfg.root / "storage" / "manual_approval" / "approval_intake_submission.json"
    actual_unlock_latest_path = latest / "operator_unlock_request.json"
    actual_unlock_archive_path = cfg.root / "storage" / "signed_testnet" / "operator_unlock_request.json"

    approval_summary = _manual_file_summary(actual_approval_path)
    unlock_latest_summary = _manual_file_summary(actual_unlock_latest_path)
    unlock_archive_summary = _manual_file_summary(actual_unlock_archive_path)
    actual_approval_present = bool(approval_summary["present"])
    actual_unlock_present = bool(unlock_latest_summary["present"] or unlock_archive_summary["present"])

    blockers: list[str] = []
    if not actual_approval_present:
        blockers.append("ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING")
    if not actual_unlock_present:
        blockers.append("ACTUAL_OPERATOR_UNLOCK_REQUEST_MISSING")
    blockers.extend([f"MISSING_SANDBOX_SOURCE_ARTIFACT:{name}" for name in missing_artifacts])
    if unsafe_flags:
        blockers.extend([f"UNSAFE_SANDBOX_SOURCE_FLAG:{name}:{','.join(flags)}" for name, flags in unsafe_flags.items()])
    for name, summary in {
        "actual_manual_approval_submission": approval_summary,
        "actual_operator_unlock_request_latest": unlock_latest_summary,
        "actual_operator_unlock_request_archive": unlock_archive_summary,
    }.items():
        unsafe = summary.get("unsafe_truthy_fields") or []
        if unsafe:
            blockers.append(f"UNSAFE_ACTUAL_INTAKE_FILE_FLAG:{name}:{','.join(unsafe)}")
    blockers = sorted(dict.fromkeys(blockers))

    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    sandbox_id = stable_id(
        "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox",
        {
            "source_hashes": {name: _artifact_hash(payload) for name, payload in artifacts.items()},
            "approval_sha256": approval_summary.get("sha256"),
            "unlock_latest_sha256": unlock_latest_summary.get("sha256"),
            "unlock_archive_sha256": unlock_archive_summary.get("sha256"),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_id": sandbox_id,
        "phase6_5_version": PHASE6_5_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "sandbox_only": True,
        "actual_intake_files_created_by_this_module": False,
        "actual_manual_approval_submission_present": actual_approval_present,
        "actual_operator_unlock_request_present": actual_unlock_present,
        "actual_manual_approval_submission_summary": approval_summary,
        "actual_operator_unlock_request_latest_summary": unlock_latest_summary,
        "actual_operator_unlock_request_archive_summary": unlock_archive_summary,
        "missing_source_artifacts": missing_artifacts,
        "unsafe_flags_by_artifact": unsafe_flags,
        "source_evidence_hash_summary": {name: _source_summary(name, payload) for name, payload in artifacts.items()},
        "sandbox_validation_sequence": _build_sandbox_sequence(),
        "phase7_entry_review_possible": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "approval_intake_validated": False,
        "operator_unlock_request_validated": False,
        "signed_testnet_preparation_ready": False,
        "signed_testnet_readiness_passed": False,
        "block_reasons": blockers,
        "recommended_next_action": "operator_must_create_actual_manual_approval_and_unlock_files_then_rerun_phase5_phase6_3_phase6_4_phase6_5" if blocked else "review_actual_intake_files_but_keep_execution_disabled_until_separate_phase7_approval",
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
    report["phase6_5_report_sha256"] = sha256_json(report)
    return report


def persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase6_5_actual_manual_approval_operator_unlock_intake_sandbox")
    report = build_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report(cfg=cfg)
    markdown = _build_operator_handoff_markdown(report)

    atomic_write_json(latest / "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report.json", report)
    atomic_write_json(latest / "actual_manual_approval_operator_unlock_intake_sandbox.json", report)
    (latest / "ACTUAL_INTAKE_SANDBOX_OPERATOR_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")
    atomic_write_json(phase_dir / "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report.json", report)
    atomic_write_json(phase_dir / "actual_manual_approval_operator_unlock_intake_sandbox.json", report)
    (phase_dir / "ACTUAL_INTAKE_SANDBOX_OPERATOR_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE6_5_REGISTRY_NAME),
        {
            "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_id": report.get("phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "actual_manual_approval_submission_present": report.get("actual_manual_approval_submission_present"),
            "actual_operator_unlock_request_present": report.get("actual_operator_unlock_request_present"),
            "phase7_entry_review_possible": False,
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
        registry_name=PHASE6_5_REGISTRY_NAME,
        id_field="phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_registry_record_id",
        hash_field="phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_registry_record_sha256",
        id_prefix="phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_registry_record",
    )
    atomic_write_json(latest / "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE6_5_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report",
    "persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report",
]
