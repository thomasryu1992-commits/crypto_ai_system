from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.research.research_signal_profile_approval import (
    STEP261_PROFILE_APPROVAL_PACKET_VERSION,
    apply_step261_approved_profile_disabled_stub,
    validate_step261_approval_packet,
)


STEP262_PROFILE_APPROVAL_INTAKE_VERSION = "step262_researchsignal_profile_approval_intake_validator_v1"

DEFAULT_STEP262_APPROVAL_INTAKE_POLICY: dict[str, Any] = {
    "mode": "approval_intake_validator_review_only",
    "approval_intake_write_enabled": True,
    "manual_approval_required": True,
    "auto_apply_approved_profile": False,
    "runtime_score_weight_write_enabled": False,
    "settings_score_weight_write_enabled": False,
    "apply_approved_profile_enabled": False,
    "accepted_decisions": ["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"],
}

_ALLOWED_DECISIONS = set(DEFAULT_STEP262_APPROVAL_INTAKE_POLICY["accepted_decisions"])
_APPROVE_DECISION = "APPROVE_FOR_REVIEW_ONLY_STAGING"
_REJECT_DECISION = "REJECT"
_MORE_DATA_DECISION = "REQUEST_MORE_DATA"


def _utc_now_iso() -> str:
    return utc_now_canonical()


def _parse_utc_timestamp(value: Any) -> bool:
    return is_canonical_utc_timestamp(value)


def _get_cfg_path(cfg: Any, path: str, default: Any = None) -> Any:
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(path, default)
    return default


def _extract_packet(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if "approval_packet" in source and isinstance(source.get("approval_packet"), Mapping):
        return source["approval_packet"]  # type: ignore[index]
    return source


def resolve_step262_approval_intake_policy(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Step262 approval-intake policy with hard safety locks.

    Step262 may validate and record operator intent. It may not write selected
    profile weights into runtime settings and may not open order routing.
    """
    policy = deepcopy(DEFAULT_STEP262_APPROVAL_INTAKE_POLICY)
    configured = _get_cfg_path(cfg, "research.calibration_approval_intake", None)
    if isinstance(configured, Mapping):
        for key in policy:
            if key in configured:
                policy[key] = configured[key]
    if overrides:
        for key in policy:
            if key in overrides:
                policy[key] = overrides[key]

    # Hard locks for Step262. Config cannot enable mutation or application.
    policy["manual_approval_required"] = True
    policy["auto_apply_approved_profile"] = False
    policy["runtime_score_weight_write_enabled"] = False
    policy["settings_score_weight_write_enabled"] = False
    policy["apply_approved_profile_enabled"] = False

    accepted = policy.get("accepted_decisions")
    if not isinstance(accepted, list) or not accepted:
        policy["accepted_decisions"] = list(DEFAULT_STEP262_APPROVAL_INTAKE_POLICY["accepted_decisions"])
    return policy


def _decision_status(decision: str, packet: Mapping[str, Any]) -> tuple[str, list[str]]:
    approval = packet.get("approval") if isinstance(packet.get("approval"), Mapping) else {}
    candidate = packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}
    approval_status = approval.get("approval_status")
    candidate_available = candidate.get("candidate_available") is True
    reasons: list[str] = []

    if decision == _APPROVE_DECISION:
        if approval_status != "pending_manual_approval":
            reasons.append("APPROVAL_PACKET_NOT_PENDING_MANUAL_APPROVAL")
        if not candidate_available:
            reasons.append("CANDIDATE_PROFILE_NOT_AVAILABLE")
        if reasons:
            return "invalid", reasons
        return "accepted_review_only_staging", ["REVIEW_ONLY_STAGING_INTENT_RECORDED"]
    if decision == _REJECT_DECISION:
        return "rejected", ["REJECTION_RECORDED"]
    if decision == _MORE_DATA_DECISION:
        return "more_data_requested", ["MORE_DATA_REQUEST_RECORDED"]
    return "invalid", ["UNKNOWN_APPROVAL_DECISION"]


def build_step262_approval_intake_record(
    step261_packet_or_report: Mapping[str, Any],
    cfg: Any = None,
    *,
    approval_decision: str,
    approver: str,
    rationale: str,
    timestamp_utc: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an approval-intake record for a Step261 packet.

    This validates and records operator intent only. It deliberately does not
    modify research.score_weights and does not trigger any execution path.
    """
    packet = _extract_packet(step261_packet_or_report)
    policy = resolve_step262_approval_intake_policy(cfg, policy_overrides)
    timestamp = timestamp_utc or _utc_now_iso()
    decision = str(approval_decision or "").strip()
    approver_name = str(approver or "").strip()
    rationale_text = str(rationale or "").strip()

    packet_validation = validate_step261_approval_packet(packet)
    packet_sha = sha256_json({k: v for k, v in packet.items() if k != "approval_packet_sha256"})
    packet_source = packet.get("source") if isinstance(packet.get("source"), Mapping) else {}
    decision_status, decision_reasons = _decision_status(decision, packet)

    validation_checks = {
        "intake_version_matches_step262": True,
        "step261_packet_version_matches": packet.get("version") == STEP261_PROFILE_APPROVAL_PACKET_VERSION,
        "step261_packet_valid": packet_validation.get("valid") is True,
        "approval_packet_id_present": bool(packet.get("approval_packet_id")),
        "approval_decision_allowed": decision in set(policy.get("accepted_decisions") or []),
        "approver_present": bool(approver_name),
        "rationale_present": bool(rationale_text),
        "timestamp_utc_canonical": _parse_utc_timestamp(timestamp),
        "timestamp_utc_parseable": _parse_utc_timestamp(timestamp),
        "approval_packet_hash_matches": packet.get("approval_packet_sha256") in {packet_sha, None} or packet.get("approval_packet_sha256") == packet_sha,
        "source_report_hash_present_when_declared": packet_source.get("source_step_report_exists") in {None, True} and packet_source.get("source_step_report_hash_matches") is not False,
        "approve_only_when_candidate_pending": decision_status != "invalid",
        "policy_blocks_auto_apply": policy.get("auto_apply_approved_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_approved_profile_enabled") is False,
    }
    valid = all(validation_checks.values())

    approval_signature_payload = {"approval_packet_id": packet.get("approval_packet_id"), "decision": decision, "approver": approver_name, "timestamp_utc": timestamp, "rationale": rationale_text}
    approval_signature = sha256_json(approval_signature_payload)
    approval_record = {
        "approval_packet_id": packet.get("approval_packet_id"),
        "approval_intake_id": stable_id("approval_intake", approval_signature_payload, 24),
        "approver_id": approver_name,
        "approver_role": str((metadata or {}).get("approver_role") or "manual_reviewer"),
        "approval_ticket_id": str((metadata or {}).get("approval_ticket_id") or ""),
        "approval_signature": approval_signature,
        "source_step_report_path": packet_source.get("source_step_report_path"),
        "source_step_report_sha256": packet_source.get("source_step_report_sha256"),
        "approval_packet_sha256": packet.get("approval_packet_sha256") or packet_sha,
        "feature_matrix_sha256": packet_source.get("feature_matrix_sha256"),
        "profile_candidate_sha256": packet_source.get("profile_candidate_sha256"),
        "approval_decision": decision,
        "approver": approver_name,
        "rationale": rationale_text,
        "timestamp_utc": timestamp,
        "recorded": valid,
        "record_status": decision_status if valid else "invalid",
        "record_reasons": decision_reasons,
        "metadata": dict(metadata or {}),
    }

    candidate = packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}
    intake_record = {
        "step": 262,
        "version": STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
        "created_at_utc": _utc_now_iso(),
        "approval_packet_id": packet.get("approval_packet_id"),
        "approval_intake_id": approval_record["approval_intake_id"],
        "approval_signature": approval_signature,
        "approval_packet_sha256": approval_record["approval_packet_sha256"],
        "source_step_report_sha256": approval_record["source_step_report_sha256"],
        "feature_matrix_sha256": approval_record["feature_matrix_sha256"],
        "profile_candidate_sha256": approval_record["profile_candidate_sha256"],
        "source_packet_version": packet.get("version"),
        "source_packet_status": (packet.get("approval") or {}).get("approval_status") if isinstance(packet.get("approval"), Mapping) else None,
        "production_candidate_profile": candidate.get("production_candidate_profile") if isinstance(candidate, Mapping) else None,
        "candidate_available": candidate.get("candidate_available") is True if isinstance(candidate, Mapping) else False,
        "approval_record": approval_record,
        "validation": {
            "schema_version": STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
            "valid": valid,
            "checks": validation_checks,
            "failed_checks": [name for name, ok in validation_checks.items() if not ok],
            "step261_packet_validation": packet_validation,
        },
        "policy": policy,
        "decision_effect": {
            "review_only_staging_intent_recorded": valid and decision == _APPROVE_DECISION,
            "rejection_recorded": valid and decision == _REJECT_DECISION,
            "more_data_requested": valid and decision == _MORE_DATA_DECISION,
            "runtime_profile_application_allowed": False,
            "settings_profile_write_allowed": False,
            "trading_permission_changed": False,
            "order_routing_enabled": False,
        },
        "application_stub": {
            "status": "disabled_stub",
            "apply_approved_profile_enabled": False,
            "reason": "Step262 records approval intake only. Score-weight application remains deferred.",
        },
        "safety_boundaries": {
            "review_only": True,
            "approval_intake_recorded": valid,
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
    return intake_record


def validate_step262_approval_intake_record(record: Mapping[str, Any]) -> dict[str, Any]:
    validation = record.get("validation") if isinstance(record.get("validation"), Mapping) else {}
    approval_record = record.get("approval_record") if isinstance(record.get("approval_record"), Mapping) else {}
    policy = record.get("policy") if isinstance(record.get("policy"), Mapping) else {}
    safety = record.get("safety_boundaries") if isinstance(record.get("safety_boundaries"), Mapping) else {}
    effect = record.get("decision_effect") if isinstance(record.get("decision_effect"), Mapping) else {}
    application_stub = record.get("application_stub") if isinstance(record.get("application_stub"), Mapping) else {}

    checks = {
        "version_matches_step262": record.get("version") == STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
        "approval_packet_id_present": bool(record.get("approval_packet_id")),
        "validation_object_valid": validation.get("valid") is True,
        "approval_recorded_matches_validation": approval_record.get("recorded") is validation.get("valid"),
        "decision_allowed": approval_record.get("approval_decision") in set(policy.get("accepted_decisions") or []),
        "approver_present": bool(approval_record.get("approver")),
        "rationale_present": bool(approval_record.get("rationale")),
        "timestamp_utc_canonical": _parse_utc_timestamp(approval_record.get("timestamp_utc")),
        "timestamp_utc_parseable": _parse_utc_timestamp(approval_record.get("timestamp_utc")),
        "approval_intake_id_present": bool(record.get("approval_intake_id") or approval_record.get("approval_intake_id")),
        "approval_signature_present": bool(record.get("approval_signature") or approval_record.get("approval_signature")),
        "approval_packet_hash_present": bool(record.get("approval_packet_sha256") or approval_record.get("approval_packet_sha256")),
        "policy_blocks_auto_apply": policy.get("auto_apply_approved_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_approved_profile_enabled") is False,
        "decision_effect_blocks_application": effect.get("runtime_profile_application_allowed") is False and effect.get("settings_profile_write_allowed") is False,
        "application_stub_disabled": application_stub.get("status") == "disabled_stub" and application_stub.get("apply_approved_profile_enabled") is False,
        "safety_blocks_runtime_mutation": safety.get("runtime_score_weights_mutated") is False,
        "safety_blocks_settings_mutation": safety.get("settings_score_weights_mutated") is False,
        "safety_blocks_live_trading": safety.get("live_trading_allowed") is False and safety.get("order_routing_enabled") is False,
        "missing_canonical_module_count_locked": safety.get("missing_canonical_module_count") == 2,
    }
    return {
        "schema_version": STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
        "valid": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
    }


def apply_step262_approval_intake_disabled_stub(record: Mapping[str, Any], cfg: Any = None) -> dict[str, Any]:
    """Disabled Step262 application surface.

    A valid APPROVE_FOR_REVIEW_ONLY_STAGING record still cannot change runtime
    weights in this step. This wrapper locks that boundary in tests.
    """
    original_weights = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else {}
    step261_stub = apply_step261_approved_profile_disabled_stub(
        {
            "approval_packet_id": record.get("approval_packet_id"),
            "candidate": {"production_candidate_profile": record.get("production_candidate_profile")},
        },
        cfg,
    )
    return {
        "status": "DISABLED_STUB",
        "reason": "Step262 approval intake is an audit record only; runtime score-weight application remains disabled.",
        "approval_packet_id": record.get("approval_packet_id"),
        "approval_decision": (record.get("approval_record") or {}).get("approval_decision") if isinstance(record.get("approval_record"), Mapping) else None,
        "record_status": (record.get("approval_record") or {}).get("record_status") if isinstance(record.get("approval_record"), Mapping) else None,
        "step261_stub_status": step261_stub.get("status"),
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
