from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.common import (
    hash_without as _hash_payload_without,
    latest_dir as _latest_dir,
    read_latest_json as _read_latest_json,
    storage_dir as _storage_dir,
    verify_embedded_hash as _verify_embedded_hash,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE5_1_VERSION = "phase5_1_manual_approval_operator_handoff_v1"
PHASE5_1_REGISTRY_NAME = "phase5_1_manual_approval_operator_handoff_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE5_1_MANUAL_APPROVAL_OPERATOR_HANDOFF_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE5_1_MANUAL_APPROVAL_OPERATOR_HANDOFF_BLOCKED_REVIEW_ONLY"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
APPROVAL_INTAKE_SUBMITTED_BY_THIS_MODULE = False
APPROVAL_INTAKE_VALIDATED_BY_THIS_MODULE = False
SIGNED_TESTNET_UNLOCK_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False


def _required_source_blockers(phase4_4: Mapping[str, Any], phase5: Mapping[str, Any], approval_draft: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if phase4_4.get("status") != "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE4_4_REVIEW_PACKET_NOT_READY")
    if phase5.get("status") != "PHASE5_MANUAL_APPROVAL_INTAKE_BLOCKED_REVIEW_ONLY":
        blockers.append("PHASE5_EXPECTED_BLOCKED_STATE_NOT_FOUND")
    if phase5.get("approval_intake_validated") is not False:
        blockers.append("PHASE5_APPROVAL_INTAKE_UNEXPECTEDLY_VALIDATED")
    if phase5.get("signed_testnet_unlock_allowed") is not False:
        blockers.append("PHASE5_SIGNED_TESTNET_UNLOCK_UNEXPECTEDLY_ALLOWED")
    if not approval_draft:
        blockers.append("APPROVAL_PACKET_DRAFT_MISSING")
    else:
        if approval_draft.get("status") != "APPROVAL_PACKET_DRAFT_REVIEW_ONLY_NOT_APPROVED":
            blockers.append("APPROVAL_PACKET_DRAFT_STATUS_INVALID")
        if not _verify_embedded_hash(approval_draft, "approval_packet_draft_sha256"):
            blockers.append("APPROVAL_PACKET_DRAFT_HASH_INVALID")
    return blockers


def _build_submission_template(*, approval_draft: Mapping[str, Any], phase5_report: Mapping[str, Any], created: str) -> dict[str, Any]:
    approval_packet_hash = approval_draft.get("approval_packet_draft_sha256")
    source_report_hash = approval_draft.get("source_report_hash")
    feature_matrix_hash = approval_draft.get("feature_matrix_sha256")
    profile_candidate_hash = approval_draft.get("profile_candidate_hash")
    candidate_profile_id = approval_draft.get("candidate_profile_id")
    approval_packet_draft_id = approval_draft.get("approval_packet_draft_id")

    template = {
        "template_type": "manual_approval_intake_submission_template",
        "template_version": PHASE5_1_VERSION,
        "review_only": True,
        "operator_action_required": True,
        "write_target_when_manually_approved": "storage/manual_approval/approval_intake_submission.json",
        "do_not_write_automatically": True,
        "instructions": [
            "Copy this template only after a human approval review is complete.",
            "Fill approver_info and ticket_or_signature manually.",
            "Do not change source_report_hash, approval_packet_hash, feature_matrix_hash, or profile_candidate_hash unless the source artifacts are regenerated and re-reviewed.",
            "Saving this template itself is not approval and does not unlock signed testnet execution.",
        ],
        "approval_packet_id": "MANUAL_REQUIRED_APPROVAL_PACKET_ID",
        "approval_intake_id": "MANUAL_REQUIRED_APPROVAL_INTAKE_ID",
        "approver_info": "MANUAL_REQUIRED_APPROVER_NAME_OR_HANDLE",
        "ticket_or_signature": "MANUAL_REQUIRED_TICKET_OR_SIGNATURE",
        "source_report_hash": source_report_hash,
        "approval_packet_hash": approval_packet_hash,
        "feature_matrix_hash": feature_matrix_hash,
        "profile_candidate_hash": profile_candidate_hash,
        "canonical_utc_timestamp": "MANUAL_REQUIRED_CANONICAL_UTC_TIMESTAMP",
        "approval_scope": "review_only_candidate_profile_manual_intake",
        "candidate_profile_id": candidate_profile_id,
        "approval_packet_draft_id": approval_packet_draft_id,
        "phase5_manual_approval_intake_validation_id": phase5_report.get("phase5_manual_approval_intake_validation_id"),
        "manual_checks_required": [
            "Confirm candidate profile hash matches the review packet.",
            "Confirm feature matrix hash matches the data lineage artifacts.",
            "Confirm source report hash matches the Phase 4.3 score-bucket replay report.",
            "Confirm all execution flags are false before submission.",
            "Confirm this approval is for signed-testnet preparation only, not live trading.",
        ],
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_trading_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    template["manual_approval_submission_template_sha256"] = sha256_json(template)
    return template


def _build_handoff_markdown(template: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    required = template.get("manual_checks_required", [])
    required_lines = "\n".join(f"- {item}" for item in required)
    return f"""# Phase 5.1 Manual Approval Operator Handoff — Review Only

Status: `{report.get('status')}`

This handoff prepares the human operator material required before any manual approval intake submission. It does not create an approval packet, does not submit approval intake, and does not unlock signed testnet or live execution.

## Template Location

- Review-only template: `storage/latest/manual_approval_submission_template_review_only.json`
- Operator copy target, only after manual approval: `storage/manual_approval/approval_intake_submission.json`

## Required Manual Fields

- `approval_packet_id`
- `approval_intake_id`
- `approver_info`
- `ticket_or_signature`
- `canonical_utc_timestamp`

## Hashes That Must Not Be Changed

- `source_report_hash`: `{template.get('source_report_hash')}`
- `approval_packet_hash`: `{template.get('approval_packet_hash')}`
- `feature_matrix_hash`: `{template.get('feature_matrix_hash')}`
- `profile_candidate_hash`: `{template.get('profile_candidate_hash')}`

## Manual Checks

{required_lines}

## Safety Invariants

- `signed_testnet_unlock_allowed=false`
- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `live_trading_allowed=false`
- `runtime_settings_mutated=false`
- `score_weights_mutated=false`
- `external_order_submission_performed=false`
- `auto_promotion_allowed=false`

## Next Step

After a human manually creates `storage/manual_approval/approval_intake_submission.json`, rerun `python scripts/build_phase5_manual_approval_intake_validation.py`. If any required field or hash does not match, Phase 5 must remain fail-closed.
"""


def build_phase5_1_manual_approval_operator_handoff_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    phase4_4 = _read_latest_json(cfg, "phase4_4_candidate_profile_review_packet_report.json")
    phase5 = _read_latest_json(cfg, "phase5_manual_approval_intake_validation_report.json")
    approval_draft = _read_latest_json(cfg, "approval_packet_draft_review_only.json")
    created = utc_now_canonical()
    blockers = _required_source_blockers(phase4_4, phase5, approval_draft)
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    seed = {
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "phase5_manual_approval_intake_validation_id": phase5.get("phase5_manual_approval_intake_validation_id"),
        "created_at_utc": created,
        "blocked": blocked,
    }
    handoff_id = stable_id("phase5_1_manual_approval_operator_handoff", seed, 24)
    template = _build_submission_template(approval_draft=approval_draft, phase5_report=phase5, created=created) if approval_draft else {}

    report: dict[str, Any] = {
        "phase5_1_manual_approval_operator_handoff_id": handoff_id,
        "phase5_1_version": PHASE5_1_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "manual_approval_submission_template_created": bool(template),
        "manual_approval_submission_created": False,
        "approval_intake_submitted": False,
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "approval_packet_draft_sha256": approval_draft.get("approval_packet_draft_sha256"),
        "manual_template_sha256": template.get("manual_approval_submission_template_sha256"),
        "manual_submission_template_path": "storage/latest/manual_approval_submission_template_review_only.json",
        "manual_submission_actual_target_path": "storage/manual_approval/approval_intake_submission.json",
        "operator_handoff_markdown_path": "storage/phase5_1_manual_approval_operator_handoff/MANUAL_APPROVAL_OPERATOR_HANDOFF_REVIEW_ONLY.md",
        "source_report_hash": approval_draft.get("source_report_hash"),
        "feature_matrix_hash": approval_draft.get("feature_matrix_sha256"),
        "profile_candidate_hash": approval_draft.get("profile_candidate_hash"),
        "block_reasons": blockers,
        "recommended_next_action": "operator_review_and_manual_submission_if_approved" if not blocked else "repair_review_packet_before_operator_handoff",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_execution_unlock_authority": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    report["phase5_1_report_sha256"] = sha256_json(report)
    return report


def persist_phase5_1_manual_approval_operator_handoff_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase5_1_manual_approval_operator_handoff")
    manual_dir = _storage_dir(cfg, "storage/manual_approval")
    report = build_phase5_1_manual_approval_operator_handoff_report(cfg=cfg)
    approval_draft = _read_latest_json(cfg, "approval_packet_draft_review_only.json")
    phase5 = _read_latest_json(cfg, "phase5_manual_approval_intake_validation_report.json")
    template = _build_submission_template(approval_draft=approval_draft, phase5_report=phase5, created=report["created_at_utc"]) if approval_draft else {}

    atomic_write_json(latest / "phase5_1_manual_approval_operator_handoff_report.json", report)
    atomic_write_json(phase_dir / "phase5_1_manual_approval_operator_handoff_report.json", report)
    if template:
        atomic_write_json(latest / "manual_approval_submission_template_review_only.json", template)
        atomic_write_json(phase_dir / "manual_approval_submission_template_review_only.json", template)
        # Deliberately write a template name only. Do not create the actual submission file that Phase 5 consumes.
        atomic_write_json(manual_dir / "approval_intake_submission_TEMPLATE_REVIEW_ONLY.json", template)
        handoff_md = _build_handoff_markdown(template, report)
        (phase_dir / "MANUAL_APPROVAL_OPERATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff_md, encoding="utf-8")
        (latest / "MANUAL_APPROVAL_OPERATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff_md, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE5_1_REGISTRY_NAME),
        {
            "phase5_1_manual_approval_operator_handoff_id": report.get("phase5_1_manual_approval_operator_handoff_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "manual_approval_submission_template_created": report.get("manual_approval_submission_template_created"),
            "manual_approval_submission_created": False,
            "approval_intake_submitted": False,
            "approval_intake_validated": False,
            "approval_packet_created": False,
            "signed_testnet_unlock_allowed": False,
            "testnet_order_submission_allowed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE5_1_REGISTRY_NAME,
        id_field="phase5_1_manual_approval_operator_handoff_registry_record_id",
        hash_field="phase5_1_manual_approval_operator_handoff_registry_record_sha256",
        id_prefix="phase5_1_manual_approval_operator_handoff_registry_record",
    )
    atomic_write_json(latest / "phase5_1_manual_approval_operator_handoff_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase5_1_manual_approval_operator_handoff_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE5_1_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase5_1_manual_approval_operator_handoff_report",
    "persist_phase5_1_manual_approval_operator_handoff_report",
]
