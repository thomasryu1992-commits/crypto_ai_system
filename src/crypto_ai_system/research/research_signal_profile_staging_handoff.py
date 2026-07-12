from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from crypto_ai_system.research.research_signal_profile_approval_intake import (
    STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
    apply_step262_approval_intake_disabled_stub,
    validate_step262_approval_intake_record,
)


STEP263_PROFILE_STAGING_HANDOFF_VERSION = "step263_researchsignal_profile_review_only_staging_handoff_v1"

DEFAULT_STEP263_STAGING_HANDOFF_POLICY: dict[str, Any] = {
    "mode": "review_only_staging_handoff_pre_apply_checklist",
    "staging_handoff_write_enabled": True,
    "manual_pre_apply_review_required": True,
    "pre_apply_checklist_required": True,
    "auto_apply_approved_profile": False,
    "runtime_score_weight_write_enabled": False,
    "settings_score_weight_write_enabled": False,
    "apply_approved_profile_enabled": False,
    "accepted_source_decisions": ["APPROVE_FOR_REVIEW_ONLY_STAGING"],
}

_READY_STATUS = "ready_for_pre_apply_review"
_BLOCKED_STATUS = "blocked_by_approval_intake"
_INVALID_STATUS = "invalid_source_intake"
_ALLOWED_HANDOFF_STATUSES = {_READY_STATUS, _BLOCKED_STATUS, _INVALID_STATUS}
_APPROVE_DECISION = "APPROVE_FOR_REVIEW_ONLY_STAGING"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_cfg_path(cfg: Any, path: str, default: Any = None) -> Any:
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(path, default)
    return default


def _extract_intake_record(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if "approval_intake_record" in source and isinstance(source.get("approval_intake_record"), Mapping):
        return source["approval_intake_record"]  # type: ignore[index]
    return source


def _stable_handoff_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "step263_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def resolve_step263_staging_handoff_policy(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Step263 staging handoff policy with non-mutation hard locks."""
    policy = deepcopy(DEFAULT_STEP263_STAGING_HANDOFF_POLICY)
    configured = _get_cfg_path(cfg, "research.calibration_staging_handoff", None)
    if isinstance(configured, Mapping):
        for key in policy:
            if key in configured:
                policy[key] = configured[key]
    if overrides:
        for key in policy:
            if key in overrides:
                policy[key] = overrides[key]

    # Hard locks: a staging handoff can never become runtime application in Step263.
    policy["manual_pre_apply_review_required"] = True
    policy["pre_apply_checklist_required"] = True
    policy["auto_apply_approved_profile"] = False
    policy["runtime_score_weight_write_enabled"] = False
    policy["settings_score_weight_write_enabled"] = False
    policy["apply_approved_profile_enabled"] = False
    accepted = policy.get("accepted_source_decisions")
    if not isinstance(accepted, list) or not accepted:
        policy["accepted_source_decisions"] = list(DEFAULT_STEP263_STAGING_HANDOFF_POLICY["accepted_source_decisions"])
    return policy


def _approval_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return record.get("approval_record") if isinstance(record.get("approval_record"), Mapping) else {}


def _source_is_ready_for_staging(record: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[bool, list[str]]:
    validation = validate_step262_approval_intake_record(record)
    approval = _approval_record(record)
    reasons: list[str] = []
    decision = approval.get("approval_decision")
    record_status = approval.get("record_status")

    if validation.get("valid") is not True:
        reasons.append("SOURCE_STEP262_INTAKE_VALIDATION_FAILED")
    if record.get("version") != STEP262_PROFILE_APPROVAL_INTAKE_VERSION:
        reasons.append("SOURCE_STEP262_VERSION_MISMATCH")
    if decision not in set(policy.get("accepted_source_decisions") or []):
        reasons.append("SOURCE_DECISION_NOT_APPROVED_FOR_STAGING")
    if decision != _APPROVE_DECISION:
        reasons.append("APPROVE_FOR_REVIEW_ONLY_STAGING_REQUIRED")
    if record_status != "accepted_review_only_staging":
        reasons.append("SOURCE_RECORD_STATUS_NOT_ACCEPTED_REVIEW_ONLY_STAGING")
    if approval.get("recorded") is not True:
        reasons.append("SOURCE_APPROVAL_INTAKE_NOT_RECORDED")
    if record.get("candidate_available") is not True:
        reasons.append("CANDIDATE_PROFILE_NOT_AVAILABLE")
    if not record.get("production_candidate_profile"):
        reasons.append("PRODUCTION_CANDIDATE_PROFILE_MISSING")
    return not reasons, reasons


def _candidate_weights_from_intake(record: Mapping[str, Any]) -> dict[str, Any]:
    # Step262 stores the candidate name but not full weights. Preserve a stable
    # schema field and leave it empty when the source report did not carry the
    # Step261 candidate payload. The pre-apply checklist makes this explicit.
    candidate = record.get("candidate") if isinstance(record.get("candidate"), Mapping) else {}
    weights = candidate.get("candidate_weights") if isinstance(candidate, Mapping) else None
    return dict(weights or {}) if isinstance(weights, Mapping) else {}


def _build_pre_apply_checklist(record: Mapping[str, Any], *, source_ready: bool, source_reasons: list[str]) -> list[dict[str, Any]]:
    approval = _approval_record(record)
    source_validation = validate_step262_approval_intake_record(record)
    candidate_weights = _candidate_weights_from_intake(record)
    items = [
        {
            "id": "source_step262_intake_valid",
            "label": "Step262 approval-intake record validates successfully.",
            "passed": source_validation.get("valid") is True,
        },
        {
            "id": "approval_intake_is_review_only_staging",
            "label": "Approval decision is APPROVE_FOR_REVIEW_ONLY_STAGING and is explicitly not runtime apply approval.",
            "passed": approval.get("approval_decision") == _APPROVE_DECISION and approval.get("record_status") == "accepted_review_only_staging",
        },
        {
            "id": "candidate_profile_available",
            "label": "Production candidate profile is available from a real or explicit Feature Store matrix review.",
            "passed": record.get("candidate_available") is True and bool(record.get("production_candidate_profile")),
        },
        {
            "id": "candidate_weights_present_or_deferred",
            "label": "Candidate weights are present on the handoff or must be reloaded from the Step260/Step261 packet before any future apply step.",
            "passed": source_ready or bool(candidate_weights),
            "note": "Step263 still does not apply weights; this check gates only review-only staging handoff readiness.",
        },
        {
            "id": "manual_pre_apply_review_required",
            "label": "A separate manual pre-apply review is required before any later apply implementation can be considered.",
            "passed": True,
        },
        {
            "id": "runtime_score_weight_write_disabled",
            "label": "Runtime research.score_weights mutation remains disabled.",
            "passed": True,
        },
        {
            "id": "settings_score_weight_write_disabled",
            "label": "settings.yaml score-weight write remains disabled.",
            "passed": True,
        },
        {
            "id": "execution_routing_disabled",
            "label": "Live/testnet order routing remains disabled and external order submission is impossible in this step.",
            "passed": True,
        },
    ]
    if not source_ready:
        items.append({
            "id": "source_block_reasons_empty",
            "label": "No source-intake blocking reason is present.",
            "passed": False,
            "failed_reasons": list(source_reasons),
        })
    return items


def build_step263_review_only_staging_handoff_packet(
    step262_intake_or_report: Mapping[str, Any],
    cfg: Any = None,
    *,
    operator_label: str = "manual_reviewer",
    notes: str = "",
    timestamp_utc: str | None = None,
    policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a review-only staging handoff packet from an approved Step262 record.

    This is a pre-apply review artifact. It cannot mutate runtime score weights,
    cannot write settings.yaml, and cannot enable any execution path.
    """
    record = _extract_intake_record(step262_intake_or_report)
    policy = resolve_step263_staging_handoff_policy(cfg, policy_overrides)
    source_ready, source_reasons = _source_is_ready_for_staging(record, policy)
    source_validation = validate_step262_approval_intake_record(record)
    approval = _approval_record(record)
    candidate_weights = _candidate_weights_from_intake(record)

    if source_validation.get("valid") is not True:
        handoff_status = _INVALID_STATUS
    elif source_ready:
        handoff_status = _READY_STATUS
    else:
        handoff_status = _BLOCKED_STATUS

    checklist = _build_pre_apply_checklist(record, source_ready=source_ready, source_reasons=source_reasons)
    checklist_summary = {
        "total": len(checklist),
        "passed": sum(1 for item in checklist if item.get("passed") is True),
        "failed": sum(1 for item in checklist if item.get("passed") is not True),
        "all_passed": all(item.get("passed") is True for item in checklist),
    }
    identity_payload = {
        "version": STEP263_PROFILE_STAGING_HANDOFF_VERSION,
        "source_step": 262,
        "approval_packet_id": record.get("approval_packet_id"),
        "approval_decision": approval.get("approval_decision"),
        "record_status": approval.get("record_status"),
        "production_candidate_profile": record.get("production_candidate_profile"),
        "handoff_status": handoff_status,
    }

    packet = {
        "step": 263,
        "version": STEP263_PROFILE_STAGING_HANDOFF_VERSION,
        "staging_handoff_id": _stable_handoff_id(identity_payload),
        "created_at_utc": _utc_now_iso(),
        "operator_label": str(operator_label),
        "notes": str(notes),
        "source": {
            "source_step": 262,
            "source_version": record.get("version"),
            "approval_packet_id": record.get("approval_packet_id"),
            "approval_decision": approval.get("approval_decision"),
            "approval_record_status": approval.get("record_status"),
            "approval_recorded": approval.get("recorded") is True,
            "source_validation_valid": source_validation.get("valid") is True,
        },
        "candidate": {
            "candidate_available": record.get("candidate_available") is True,
            "production_candidate_profile": record.get("production_candidate_profile"),
            "candidate_weights": candidate_weights,
            "candidate_weights_present": bool(candidate_weights),
            "candidate_weights_reload_required_before_future_apply": not bool(candidate_weights),
        },
        "handoff": {
            "handoff_status": handoff_status,
            "ready_for_pre_apply_review": handoff_status == _READY_STATUS,
            "blocked_reasons": source_reasons,
            "pre_apply_checklist_required": True,
            "pre_apply_checklist": checklist,
            "pre_apply_checklist_summary": checklist_summary,
            "pre_apply_schema": {
                "required_fields": [
                    "staging_handoff_id",
                    "approval_packet_id",
                    "production_candidate_profile",
                    "candidate_weights",
                    "pre_apply_checklist",
                    "manual_pre_apply_reviewer",
                    "manual_pre_apply_rationale",
                ],
                "allowed_next_decisions": ["READY_FOR_DISABLED_PRE_APPLY_REVIEW", "REJECT_STAGING_HANDOFF", "REQUEST_MORE_DATA"],
                "decision_note": "Step263 is a staging handoff only. It does not approve or execute score_weights application.",
            },
        },
        "policy": policy,
        "application_stub": {
            "status": "disabled_stub",
            "apply_staging_handoff_enabled": False,
            "reason": "Step263 creates a pre-apply staging handoff only. Runtime score-weight application remains disabled.",
        },
        "safety_boundaries": {
            "review_only": True,
            "manual_pre_apply_review_required": True,
            "auto_apply_selected_profile": False,
            "selected_profile_written_to_settings": False,
            "runtime_score_weights_mutated": False,
            "settings_score_weights_mutated": False,
            "production_profile_auto_applied": False,
            "config_mutated": False,
            "live_trading_allowed": False,
            "order_routing_enabled": False,
            "external_order_submission_performed": False,
            "canonical_live_execution_port_performed": False,
            "canonical_testnet_execution_port_performed": False,
            "root_package_deletion_performed": False,
            "root_package_deletion_deferred": True,
            "missing_canonical_module_count": 2,
        },
    }
    return packet


def validate_step263_staging_handoff_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    handoff = packet.get("handoff") if isinstance(packet.get("handoff"), Mapping) else {}
    candidate = packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}
    policy = packet.get("policy") if isinstance(packet.get("policy"), Mapping) else {}
    safety = packet.get("safety_boundaries") if isinstance(packet.get("safety_boundaries"), Mapping) else {}
    application_stub = packet.get("application_stub") if isinstance(packet.get("application_stub"), Mapping) else {}
    source = packet.get("source") if isinstance(packet.get("source"), Mapping) else {}
    checklist = handoff.get("pre_apply_checklist") if isinstance(handoff.get("pre_apply_checklist"), list) else []
    summary = handoff.get("pre_apply_checklist_summary") if isinstance(handoff.get("pre_apply_checklist_summary"), Mapping) else {}
    status = handoff.get("handoff_status")

    checks = {
        "version_matches_step263": packet.get("version") == STEP263_PROFILE_STAGING_HANDOFF_VERSION,
        "staging_handoff_id_present": bool(packet.get("staging_handoff_id")),
        "approval_packet_id_present": bool(source.get("approval_packet_id")),
        "handoff_status_allowed": status in _ALLOWED_HANDOFF_STATUSES,
        "checklist_present": bool(checklist),
        "checklist_summary_consistent": summary.get("total") == len(checklist) and summary.get("failed") == sum(1 for item in checklist if not item.get("passed")),
        "ready_requires_candidate_available": status != _READY_STATUS or (candidate.get("candidate_available") is True and bool(candidate.get("production_candidate_profile"))),
        "ready_requires_source_approval": status != _READY_STATUS or (source.get("approval_decision") == _APPROVE_DECISION and source.get("approval_record_status") == "accepted_review_only_staging"),
        "ready_requires_checklist_passed": status != _READY_STATUS or summary.get("all_passed") is True,
        "policy_blocks_auto_apply": policy.get("auto_apply_approved_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_approved_profile_enabled") is False,
        "application_stub_disabled": application_stub.get("status") == "disabled_stub" and application_stub.get("apply_staging_handoff_enabled") is False,
        "safety_blocks_runtime_mutation": safety.get("runtime_score_weights_mutated") is False,
        "safety_blocks_settings_mutation": safety.get("settings_score_weights_mutated") is False,
        "safety_blocks_live_trading": safety.get("live_trading_allowed") is False and safety.get("order_routing_enabled") is False,
        "missing_canonical_module_count_locked": safety.get("missing_canonical_module_count") == 2,
    }
    return {
        "schema_version": STEP263_PROFILE_STAGING_HANDOFF_VERSION,
        "valid": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
    }


def apply_step263_staging_handoff_disabled_stub(packet: Mapping[str, Any], cfg: Any = None) -> dict[str, Any]:
    """Disabled Step263 apply surface.

    Even a ready_for_pre_apply_review handoff cannot write score weights in this
    step. This function intentionally returns a non-mutating stub result.
    """
    original_weights = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else {}
    step262_stub = apply_step262_approval_intake_disabled_stub(
        {
            "approval_packet_id": (packet.get("source") or {}).get("approval_packet_id") if isinstance(packet.get("source"), Mapping) else packet.get("approval_packet_id"),
            "production_candidate_profile": (packet.get("candidate") or {}).get("production_candidate_profile") if isinstance(packet.get("candidate"), Mapping) else None,
            "approval_record": {"approval_decision": (packet.get("source") or {}).get("approval_decision") if isinstance(packet.get("source"), Mapping) else None},
        },
        cfg,
    )
    return {
        "status": "DISABLED_STUB",
        "reason": "Step263 staging handoff is pre-apply review only; runtime score-weight application remains disabled.",
        "staging_handoff_id": packet.get("staging_handoff_id"),
        "approval_packet_id": (packet.get("source") or {}).get("approval_packet_id") if isinstance(packet.get("source"), Mapping) else None,
        "handoff_status": (packet.get("handoff") or {}).get("handoff_status") if isinstance(packet.get("handoff"), Mapping) else None,
        "step262_stub_status": step262_stub.get("status"),
        "auto_apply_selected_profile": False,
        "selected_profile_written_to_settings": False,
        "runtime_score_weights_mutated": False,
        "settings_score_weights_mutated": False,
        "config_mutated": False,
        "score_weights_before": original_weights,
        "score_weights_after": original_weights,
        "live_trading_allowed": False,
        "order_routing_enabled": False,
        "external_order_submission_performed": False,
    }
