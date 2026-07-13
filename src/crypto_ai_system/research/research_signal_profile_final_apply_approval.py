from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.research.research_signal_profile_apply_dry_run import (
    STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
    apply_step265_disabled_apply_candidate_dry_run_stub,
    validate_step265_disabled_apply_candidate_dry_run_packet,
)


STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION = "step266_researchsignal_profile_final_manual_apply_approval_validator_v1"

DEFAULT_STEP266_FINAL_APPLY_APPROVAL_POLICY: dict[str, Any] = {
    "mode": "final_manual_apply_approval_validator_disabled_apply",
    "final_apply_approval_record_write_enabled": True,
    "manual_final_apply_approval_required": True,
    "auto_apply_approved_profile": False,
    "runtime_score_weight_write_enabled": False,
    "settings_score_weight_write_enabled": False,
    "apply_approved_profile_enabled": False,
    "accepted_decisions": ["APPROVE_DRY_RUN", "REJECT", "REQUEST_MORE_DATA"],
    "canonical_approve_decision": "APPROVED_DISABLED_APPLY_DRY_RUN",
    "accepted_source_dry_run_statuses": ["ready_disabled_apply_dry_run"],
}

_APPROVE_INPUT_DECISION = "APPROVE_DRY_RUN"
_APPROVE_CANONICAL_DECISION = "APPROVED_DISABLED_APPLY_DRY_RUN"
_REJECT_DECISION = "REJECT"
_MORE_DATA_DECISION = "REQUEST_MORE_DATA"
_APPROVED_RECORD_STATUS = "approved_disabled_apply_dry_run"
_REJECTED_RECORD_STATUS = "rejected_final_apply_approval"
_MORE_DATA_RECORD_STATUS = "more_data_requested"
_INVALID_RECORD_STATUS = "invalid"
_ALLOWED_RECORD_STATUSES = {
    _APPROVED_RECORD_STATUS,
    _REJECTED_RECORD_STATUS,
    _MORE_DATA_RECORD_STATUS,
    _INVALID_RECORD_STATUS,
}


def _utc_now_iso() -> str:
    return utc_now_canonical()


def _parse_utc_timestamp(value: Any) -> bool:
    return is_canonical_utc_timestamp(value)


def _get_cfg_path(cfg: Any, path: str, default: Any = None) -> Any:
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(path, default)
    return default


def _extract_dry_run_packet(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if "apply_dry_run_packet" in source and isinstance(source.get("apply_dry_run_packet"), Mapping):
        return source["apply_dry_run_packet"]  # type: ignore[index]
    return source


def _stable_final_approval_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "step266_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def resolve_step266_final_apply_approval_policy(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Step266 final manual approval policy with hard disabled-apply locks."""
    policy = deepcopy(DEFAULT_STEP266_FINAL_APPLY_APPROVAL_POLICY)
    configured = _get_cfg_path(cfg, "research.calibration_final_apply_approval", None)
    if isinstance(configured, Mapping):
        for key in policy:
            if key in configured:
                policy[key] = configured[key]
    if overrides:
        for key in policy:
            if key in overrides:
                policy[key] = overrides[key]

    # Hard locks: Step266 records final manual intent only. It cannot write or apply weights.
    policy["manual_final_apply_approval_required"] = True
    policy["auto_apply_approved_profile"] = False
    policy["runtime_score_weight_write_enabled"] = False
    policy["settings_score_weight_write_enabled"] = False
    policy["apply_approved_profile_enabled"] = False
    policy["canonical_approve_decision"] = _APPROVE_CANONICAL_DECISION

    accepted = policy.get("accepted_decisions")
    if not isinstance(accepted, list) or not accepted:
        policy["accepted_decisions"] = list(DEFAULT_STEP266_FINAL_APPLY_APPROVAL_POLICY["accepted_decisions"])
    accepted_statuses = policy.get("accepted_source_dry_run_statuses")
    if not isinstance(accepted_statuses, list) or not accepted_statuses:
        policy["accepted_source_dry_run_statuses"] = list(DEFAULT_STEP266_FINAL_APPLY_APPROVAL_POLICY["accepted_source_dry_run_statuses"])
    return policy


def _normalize_decision(decision: str) -> tuple[str, str]:
    raw = str(decision or "").strip()
    upper = raw.upper()
    if upper in {_APPROVE_INPUT_DECISION, _APPROVE_CANONICAL_DECISION}:
        return _APPROVE_INPUT_DECISION, _APPROVE_CANONICAL_DECISION
    if upper in {_REJECT_DECISION, "REJECT_DRY_RUN", "REJECT_FINAL_APPLY"}:
        return _REJECT_DECISION, _REJECT_DECISION
    if upper == _MORE_DATA_DECISION:
        return _MORE_DATA_DECISION, _MORE_DATA_DECISION
    return raw, raw


def _dry_run(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    return packet.get("dry_run") if isinstance(packet.get("dry_run"), Mapping) else {}


def _candidate(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    return packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}


def _mutation_plan(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    return packet.get("mutation_plan") if isinstance(packet.get("mutation_plan"), Mapping) else {}


def _diff(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    return packet.get("diff") if isinstance(packet.get("diff"), Mapping) else {}


def _decision_status(canonical_decision: str, packet: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[str, list[str]]:
    dry_run = _dry_run(packet)
    candidate = _candidate(packet)
    plan = _mutation_plan(packet)
    diff = _diff(packet)
    accepted_source_statuses = set(policy.get("accepted_source_dry_run_statuses") or [])
    reasons: list[str] = []

    if canonical_decision == _APPROVE_CANONICAL_DECISION:
        if dry_run.get("dry_run_status") not in accepted_source_statuses:
            reasons.append("SOURCE_DRY_RUN_NOT_READY_FOR_FINAL_APPROVAL")
        if dry_run.get("ready_for_disabled_apply_dry_run") is not True:
            reasons.append("READY_FOR_DISABLED_APPLY_DRY_RUN_FLAG_FALSE")
        if candidate.get("candidate_available") is not True:
            reasons.append("CANDIDATE_PROFILE_NOT_AVAILABLE")
        if not candidate.get("production_candidate_profile"):
            reasons.append("PRODUCTION_CANDIDATE_PROFILE_MISSING")
        if candidate.get("candidate_weights_present") is not True:
            reasons.append("CANDIDATE_WEIGHTS_NOT_PRESENT")
        if not isinstance(diff.get("details"), Mapping):
            reasons.append("SCORE_WEIGHT_DIFF_MISSING")
        if plan.get("write_enabled") is not False:
            reasons.append("MUTATION_PLAN_WRITE_MUST_BE_DISABLED")
        if plan.get("apply_enabled") is not False:
            reasons.append("MUTATION_PLAN_APPLY_MUST_BE_DISABLED")
        if dry_run.get("runtime_apply_allowed") is not False:
            reasons.append("RUNTIME_APPLY_MUST_BE_DISABLED")
        if reasons:
            return _INVALID_RECORD_STATUS, reasons
        return _APPROVED_RECORD_STATUS, ["FINAL_MANUAL_APPROVAL_RECORDED_FOR_DISABLED_DRY_RUN_ONLY"]
    if canonical_decision == _REJECT_DECISION:
        return _REJECTED_RECORD_STATUS, ["FINAL_APPLY_APPROVAL_REJECTION_RECORDED"]
    if canonical_decision == _MORE_DATA_DECISION:
        return _MORE_DATA_RECORD_STATUS, ["FINAL_APPLY_APPROVAL_MORE_DATA_REQUEST_RECORDED"]
    return _INVALID_RECORD_STATUS, ["UNKNOWN_FINAL_APPLY_APPROVAL_DECISION"]


def build_step266_final_manual_apply_approval_record(
    step265_dry_run_or_report: Mapping[str, Any],
    cfg: Any = None,
    *,
    approval_decision: str,
    approver: str,
    rationale: str,
    timestamp_utc: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a final manual apply approval record for a Step265 dry-run packet.

    APPROVE_DRY_RUN only records manual approval of the disabled dry-run packet.
    It does not apply the candidate profile, write settings, enable runtime weight
    mutation, or open any trading/execution path.
    """
    packet = _extract_dry_run_packet(step265_dry_run_or_report)
    policy = resolve_step266_final_apply_approval_policy(cfg, policy_overrides)
    timestamp = timestamp_utc or _utc_now_iso()
    input_decision, canonical_decision = _normalize_decision(approval_decision)
    approver_name = str(approver or "").strip()
    rationale_text = str(rationale or "").strip()

    dry_run_validation = validate_step265_disabled_apply_candidate_dry_run_packet(packet)
    packet_sha = sha256_json(packet)
    source = packet.get("source") if isinstance(packet.get("source"), Mapping) else {}
    candidate = _candidate(packet)
    candidate_hash = sha256_json(candidate)
    record_status, record_reasons = _decision_status(canonical_decision, packet, policy)
    accepted_decisions = set(policy.get("accepted_decisions") or [])

    validation_checks = {
        "final_apply_approval_version_matches_step266": True,
        "step265_packet_version_matches": packet.get("version") == STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
        "step265_dry_run_packet_valid": dry_run_validation.get("valid") is True,
        "apply_dry_run_id_present": bool(packet.get("apply_dry_run_id")),
        "approval_decision_allowed": input_decision in accepted_decisions,
        "approver_present": bool(approver_name),
        "rationale_present": bool(rationale_text),
        "timestamp_utc_canonical": _parse_utc_timestamp(timestamp),
        "source_packet_sha256_present": bool(packet_sha),
        "approve_only_when_dry_run_ready": record_status != _INVALID_RECORD_STATUS,
        "policy_blocks_auto_apply": policy.get("auto_apply_approved_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_approved_profile_enabled") is False,
    }
    valid = all(validation_checks.values())

    candidate = _candidate(packet)
    dry_run = _dry_run(packet)
    plan = _mutation_plan(packet)
    approval_record = {
        "apply_dry_run_id": packet.get("apply_dry_run_id"),
        "approval_packet_id": packet.get("approval_packet_id") or packet.get("apply_dry_run_id"),
        "approval_intake_id": packet.get("approval_intake_id"),
        "approver_id": approver_name,
        "approver_role": str((metadata or {}).get("approver_role") or "final_apply_reviewer"),
        "approval_ticket_id": str((metadata or {}).get("approval_ticket_id") or ""),
        "approval_signature": sha256_json({"apply_dry_run_id": packet.get("apply_dry_run_id"), "decision": input_decision, "approver": approver_name, "timestamp_utc": timestamp}),
        "source_step_report_path": source.get("source_step_report_path"),
        "source_step_report_sha256": source.get("source_step_report_sha256"),
        "approval_packet_sha256": packet_sha,
        "feature_matrix_sha256": source.get("feature_matrix_sha256") or packet.get("feature_matrix_sha256"),
        "profile_candidate_sha256": candidate.get("profile_candidate_sha256") or candidate_hash,
        "approval_decision": input_decision,
        "canonical_approval_decision": canonical_decision,
        "approver": approver_name,
        "rationale": rationale_text,
        "timestamp_utc": timestamp,
        "recorded": valid,
        "record_status": record_status if valid else _INVALID_RECORD_STATUS,
        "record_reasons": record_reasons,
        "metadata": dict(metadata or {}),
    }

    identity_payload = {
        "version": STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
        "source_step": 265,
        "apply_dry_run_id": packet.get("apply_dry_run_id"),
        "production_candidate_profile": candidate.get("production_candidate_profile"),
        "approval_decision": input_decision,
        "record_status": approval_record["record_status"],
    }
    record = {
        "step": 266,
        "version": STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
        "created_at_utc": _utc_now_iso(),
        "final_apply_approval_id": _stable_final_approval_id(identity_payload),
        "apply_dry_run_id": packet.get("apply_dry_run_id"),
        "approval_packet_id": approval_record.get("approval_packet_id"),
        "approval_intake_id": approval_record.get("approval_intake_id"),
        "approval_signature": approval_record.get("approval_signature"),
        "source_step_report_path": approval_record.get("source_step_report_path"),
        "source_step_report_sha256": approval_record.get("source_step_report_sha256"),
        "approval_packet_sha256": approval_record.get("approval_packet_sha256"),
        "feature_matrix_sha256": approval_record.get("feature_matrix_sha256"),
        "profile_candidate_sha256": approval_record.get("profile_candidate_sha256"),
        "source_dry_run_version": packet.get("version"),
        "source_dry_run_status": dry_run.get("dry_run_status"),
        "source_ready_for_disabled_apply_dry_run": dry_run.get("ready_for_disabled_apply_dry_run") is True,
        "production_candidate_profile": candidate.get("production_candidate_profile"),
        "candidate_available": candidate.get("candidate_available") is True,
        "candidate_weights_present": candidate.get("candidate_weights_present") is True,
        "mutation_plan_present": bool(plan),
        "mutation_plan_write_enabled": plan.get("write_enabled") is True,
        "mutation_plan_apply_enabled": plan.get("apply_enabled") is True,
        "final_apply_approval_record": approval_record,
        "validation": {
            "schema_version": STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
            "valid": valid,
            "checks": validation_checks,
            "failed_checks": [name for name, ok in validation_checks.items() if not ok],
            "step265_dry_run_validation": dry_run_validation,
        },
        "decision_effect": {
            "disabled_dry_run_final_approval_recorded": valid and approval_record["record_status"] == _APPROVED_RECORD_STATUS,
            "final_apply_rejection_recorded": valid and approval_record["record_status"] == _REJECTED_RECORD_STATUS,
            "more_data_requested": valid and approval_record["record_status"] == _MORE_DATA_RECORD_STATUS,
            "candidate_profile_applied": False,
            "runtime_score_weights_mutated": False,
            "settings_score_weights_mutated": False,
            "config_mutated": False,
        },
        "policy": policy,
        "application_stub": {
            "status": "disabled_stub",
            "apply_approved_profile_enabled": False,
            "reason": "Step266 records final manual approval intent only. Candidate score-weight application remains disabled.",
        },
        "safety_boundaries": {
            "review_only": True,
            "dry_run_only": True,
            "final_approval_record_only": True,
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
    return record


def validate_step266_final_manual_apply_approval_record(record: Mapping[str, Any]) -> dict[str, Any]:
    approval = record.get("final_apply_approval_record") if isinstance(record.get("final_apply_approval_record"), Mapping) else {}
    validation = record.get("validation") if isinstance(record.get("validation"), Mapping) else {}
    policy = record.get("policy") if isinstance(record.get("policy"), Mapping) else {}
    effect = record.get("decision_effect") if isinstance(record.get("decision_effect"), Mapping) else {}
    stub = record.get("application_stub") if isinstance(record.get("application_stub"), Mapping) else {}
    safety = record.get("safety_boundaries") if isinstance(record.get("safety_boundaries"), Mapping) else {}
    status = approval.get("record_status")

    checks = {
        "version_matches_step266": record.get("version") == STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
        "final_apply_approval_id_present": bool(record.get("final_apply_approval_id")),
        "apply_dry_run_id_present": bool(record.get("apply_dry_run_id")),
        "source_step265_version_matches": record.get("source_dry_run_version") == STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
        "record_status_allowed": status in _ALLOWED_RECORD_STATUSES,
        "timestamp_utc_canonical": _parse_utc_timestamp(approval.get("timestamp_utc")),
        "approval_packet_sha256_present": bool(record.get("approval_packet_sha256") or approval.get("approval_packet_sha256")),
        "profile_candidate_sha256_present": bool(record.get("profile_candidate_sha256") or approval.get("profile_candidate_sha256")),
        "internal_record_validation_valid": validation.get("valid") is True,
        "recorded_matches_validation": approval.get("recorded") is validation.get("valid"),
        "approved_requires_ready_source": status != _APPROVED_RECORD_STATUS or record.get("source_ready_for_disabled_apply_dry_run") is True,
        "approved_requires_candidate": status != _APPROVED_RECORD_STATUS or bool(record.get("production_candidate_profile")),
        "approved_requires_candidate_weights": status != _APPROVED_RECORD_STATUS or record.get("candidate_weights_present") is True,
        "mutation_plan_stays_disabled": record.get("mutation_plan_write_enabled") is False and record.get("mutation_plan_apply_enabled") is False,
        "policy_blocks_auto_apply": policy.get("auto_apply_approved_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_approved_profile_enabled") is False,
        "decision_effect_never_applies": effect.get("candidate_profile_applied") is False,
        "decision_effect_blocks_runtime_mutation": effect.get("runtime_score_weights_mutated") is False,
        "application_stub_disabled": stub.get("status") == "disabled_stub" and stub.get("apply_approved_profile_enabled") is False,
        "safety_blocks_runtime_mutation": safety.get("runtime_score_weights_mutated") is False,
        "safety_blocks_settings_mutation": safety.get("settings_score_weights_mutated") is False,
        "safety_blocks_live_trading": safety.get("live_trading_allowed") is False and safety.get("order_routing_enabled") is False,
        "missing_canonical_module_count_locked": safety.get("missing_canonical_module_count") == 2,
    }
    return {
        "schema_version": STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
        "valid": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
    }


def apply_step266_final_manual_apply_approval_disabled_stub(record: Mapping[str, Any], cfg: Any = None) -> dict[str, Any]:
    """Disabled final apply surface.

    Step266 can record that an operator approved the disabled dry-run packet, but
    it still cannot mutate score weights, write settings, or enable execution.
    """
    original_weights = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else {}
    step265_stub = apply_step265_disabled_apply_candidate_dry_run_stub(
        {
            "apply_dry_run_id": record.get("apply_dry_run_id"),
            "dry_run": {
                "dry_run_status": record.get("source_dry_run_status"),
                "ready_for_disabled_apply_dry_run": record.get("source_ready_for_disabled_apply_dry_run"),
            },
            "candidate": {
                "production_candidate_profile": record.get("production_candidate_profile"),
                "candidate_available": record.get("candidate_available"),
            },
            "source": {},
        },
        cfg,
    )
    return {
        "status": "DISABLED_STUB",
        "reason": "Step266 final manual approval is record-only; score-weight mutation and settings writes remain disabled.",
        "final_apply_approval_id": record.get("final_apply_approval_id"),
        "apply_dry_run_id": record.get("apply_dry_run_id"),
        "record_status": (record.get("final_apply_approval_record") or {}).get("record_status") if isinstance(record.get("final_apply_approval_record"), Mapping) else None,
        "production_candidate_profile": record.get("production_candidate_profile"),
        "step265_stub_status": step265_stub.get("status"),
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
