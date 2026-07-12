from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from crypto_ai_system.research.research_signal_profile_staging_handoff import (
    STEP263_PROFILE_STAGING_HANDOFF_VERSION,
    apply_step263_staging_handoff_disabled_stub,
    validate_step263_staging_handoff_packet,
)


STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION = "step264_researchsignal_profile_pre_apply_review_record_validator_v1"

DEFAULT_STEP264_PRE_APPLY_REVIEW_POLICY: dict[str, Any] = {
    "mode": "manual_pre_apply_review_record_validator_disabled_apply",
    "pre_apply_review_record_write_enabled": True,
    "manual_pre_apply_review_required": True,
    "auto_apply_reviewed_profile": False,
    "runtime_score_weight_write_enabled": False,
    "settings_score_weight_write_enabled": False,
    "apply_reviewed_profile_enabled": False,
    "accepted_decisions": ["READY", "REJECT", "REQUEST_MORE_DATA"],
    "canonical_ready_decision": "READY_FOR_DISABLED_PRE_APPLY_REVIEW",
}

_READY_INPUT_DECISION = "READY"
_READY_CANONICAL_DECISION = "READY_FOR_DISABLED_PRE_APPLY_REVIEW"
_REJECT_DECISION = "REJECT"
_MORE_DATA_DECISION = "REQUEST_MORE_DATA"
_ALLOWED_RECORD_STATUSES = {
    "ready_for_disabled_pre_apply_review",
    "rejected_pre_apply_review",
    "more_data_requested",
    "invalid",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    raw = value.strip()
    try:
        if raw.endswith("Z"):
            datetime.fromisoformat(raw[:-1] + "+00:00")
        else:
            datetime.fromisoformat(raw)
    except ValueError:
        return False
    return True


def _get_cfg_path(cfg: Any, path: str, default: Any = None) -> Any:
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(path, default)
    return default


def _extract_handoff_packet(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if "staging_handoff_packet" in source and isinstance(source.get("staging_handoff_packet"), Mapping):
        return source["staging_handoff_packet"]  # type: ignore[index]
    return source


def resolve_step264_pre_apply_review_policy(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Step264 pre-apply review policy with hard non-mutation locks."""
    policy = deepcopy(DEFAULT_STEP264_PRE_APPLY_REVIEW_POLICY)
    configured = _get_cfg_path(cfg, "research.calibration_pre_apply_review", None)
    if isinstance(configured, Mapping):
        for key in policy:
            if key in configured:
                policy[key] = configured[key]
    if overrides:
        for key in policy:
            if key in overrides:
                policy[key] = overrides[key]

    # Hard locks: Step264 records manual pre-apply review intent only.
    policy["manual_pre_apply_review_required"] = True
    policy["auto_apply_reviewed_profile"] = False
    policy["runtime_score_weight_write_enabled"] = False
    policy["settings_score_weight_write_enabled"] = False
    policy["apply_reviewed_profile_enabled"] = False
    policy["canonical_ready_decision"] = _READY_CANONICAL_DECISION

    accepted = policy.get("accepted_decisions")
    if not isinstance(accepted, list) or not accepted:
        policy["accepted_decisions"] = list(DEFAULT_STEP264_PRE_APPLY_REVIEW_POLICY["accepted_decisions"])
    return policy


def _normalize_decision(decision: str) -> tuple[str, str]:
    raw = str(decision or "").strip()
    upper = raw.upper()
    if upper in {_READY_INPUT_DECISION, _READY_CANONICAL_DECISION}:
        return _READY_INPUT_DECISION, _READY_CANONICAL_DECISION
    if upper in {_REJECT_DECISION, "REJECT_STAGING_HANDOFF"}:
        return _REJECT_DECISION, _REJECT_DECISION
    if upper == _MORE_DATA_DECISION:
        return _MORE_DATA_DECISION, _MORE_DATA_DECISION
    return raw, raw


def _handoff(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    return packet.get("handoff") if isinstance(packet.get("handoff"), Mapping) else {}


def _candidate(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    return packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}


def _source(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    return packet.get("source") if isinstance(packet.get("source"), Mapping) else {}


def _checklist_summary(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    handoff = _handoff(packet)
    return handoff.get("pre_apply_checklist_summary") if isinstance(handoff.get("pre_apply_checklist_summary"), Mapping) else {}


def _decision_status(canonical_decision: str, packet: Mapping[str, Any]) -> tuple[str, list[str]]:
    handoff = _handoff(packet)
    candidate = _candidate(packet)
    summary = _checklist_summary(packet)
    reasons: list[str] = []

    if canonical_decision == _READY_CANONICAL_DECISION:
        if handoff.get("handoff_status") != "ready_for_pre_apply_review":
            reasons.append("STAGING_HANDOFF_NOT_READY_FOR_PRE_APPLY_REVIEW")
        if handoff.get("ready_for_pre_apply_review") is not True:
            reasons.append("READY_FOR_PRE_APPLY_REVIEW_FLAG_FALSE")
        if candidate.get("candidate_available") is not True:
            reasons.append("CANDIDATE_PROFILE_NOT_AVAILABLE")
        if not candidate.get("production_candidate_profile"):
            reasons.append("PRODUCTION_CANDIDATE_PROFILE_MISSING")
        if summary.get("all_passed") is not True:
            reasons.append("PRE_APPLY_CHECKLIST_NOT_ALL_PASSED")
        if reasons:
            return "invalid", reasons
        return "ready_for_disabled_pre_apply_review", ["DISABLED_PRE_APPLY_REVIEW_READY_RECORDED"]
    if canonical_decision == _REJECT_DECISION:
        return "rejected_pre_apply_review", ["PRE_APPLY_REVIEW_REJECTION_RECORDED"]
    if canonical_decision == _MORE_DATA_DECISION:
        return "more_data_requested", ["PRE_APPLY_REVIEW_MORE_DATA_REQUEST_RECORDED"]
    return "invalid", ["UNKNOWN_PRE_APPLY_REVIEW_DECISION"]


def build_step264_pre_apply_review_record(
    step263_handoff_or_report: Mapping[str, Any],
    cfg: Any = None,
    *,
    review_decision: str,
    reviewer: str,
    rationale: str,
    timestamp_utc: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a manual pre-apply review record for a Step263 staging handoff.

    This is still a disabled-apply boundary. READY only records that the packet
    is ready for a future disabled pre-apply review stage; it cannot mutate
    research.score_weights, settings.yaml, or execution permissions.
    """
    packet = _extract_handoff_packet(step263_handoff_or_report)
    policy = resolve_step264_pre_apply_review_policy(cfg, policy_overrides)
    timestamp = timestamp_utc or _utc_now_iso()
    input_decision, canonical_decision = _normalize_decision(review_decision)
    reviewer_name = str(reviewer or "").strip()
    rationale_text = str(rationale or "").strip()

    handoff_validation = validate_step263_staging_handoff_packet(packet)
    record_status, record_reasons = _decision_status(canonical_decision, packet)
    accepted_decisions = set(policy.get("accepted_decisions") or [])

    validation_checks = {
        "pre_apply_review_version_matches_step264": True,
        "step263_packet_version_matches": packet.get("version") == STEP263_PROFILE_STAGING_HANDOFF_VERSION,
        "step263_handoff_packet_valid": handoff_validation.get("valid") is True,
        "staging_handoff_id_present": bool(packet.get("staging_handoff_id")),
        "approval_packet_id_present": bool(_source(packet).get("approval_packet_id")),
        "review_decision_allowed": input_decision in accepted_decisions,
        "reviewer_present": bool(reviewer_name),
        "rationale_present": bool(rationale_text),
        "timestamp_utc_parseable": _parse_utc_timestamp(timestamp),
        "ready_only_when_handoff_ready": record_status != "invalid",
        "policy_blocks_auto_apply": policy.get("auto_apply_reviewed_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_reviewed_profile_enabled") is False,
    }
    valid = all(validation_checks.values())

    candidate = _candidate(packet)
    handoff = _handoff(packet)
    source = _source(packet)
    review_record = {
        "staging_handoff_id": packet.get("staging_handoff_id"),
        "approval_packet_id": source.get("approval_packet_id"),
        "review_decision": input_decision,
        "canonical_review_decision": canonical_decision,
        "reviewer": reviewer_name,
        "rationale": rationale_text,
        "timestamp_utc": timestamp,
        "recorded": valid,
        "record_status": record_status if valid else "invalid",
        "record_reasons": record_reasons,
        "metadata": dict(metadata or {}),
    }

    record = {
        "step": 264,
        "version": STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
        "created_at_utc": _utc_now_iso(),
        "staging_handoff_id": packet.get("staging_handoff_id"),
        "approval_packet_id": source.get("approval_packet_id"),
        "source_handoff_version": packet.get("version"),
        "source_handoff_status": handoff.get("handoff_status"),
        "source_ready_for_pre_apply_review": handoff.get("ready_for_pre_apply_review") is True,
        "production_candidate_profile": candidate.get("production_candidate_profile"),
        "candidate_available": candidate.get("candidate_available") is True,
        "candidate_weights_present": candidate.get("candidate_weights_present") is True,
        "pre_apply_review_record": review_record,
        "validation": {
            "schema_version": STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
            "valid": valid,
            "checks": validation_checks,
            "failed_checks": [name for name, ok in validation_checks.items() if not ok],
            "step263_handoff_validation": handoff_validation,
        },
        "policy": policy,
        "decision_effect": {
            "disabled_pre_apply_review_ready_recorded": valid and record_status == "ready_for_disabled_pre_apply_review",
            "pre_apply_review_rejection_recorded": valid and record_status == "rejected_pre_apply_review",
            "more_data_requested": valid and record_status == "more_data_requested",
            "runtime_profile_application_allowed": False,
            "settings_profile_write_allowed": False,
            "trading_permission_changed": False,
            "order_routing_enabled": False,
        },
        "application_stub": {
            "status": "disabled_stub",
            "apply_pre_apply_review_enabled": False,
            "reason": "Step264 validates manual pre-apply review records only. Score-weight application remains disabled.",
        },
        "safety_boundaries": {
            "review_only": True,
            "manual_pre_apply_review_recorded": valid,
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


def validate_step264_pre_apply_review_record(record: Mapping[str, Any]) -> dict[str, Any]:
    validation = record.get("validation") if isinstance(record.get("validation"), Mapping) else {}
    review = record.get("pre_apply_review_record") if isinstance(record.get("pre_apply_review_record"), Mapping) else {}
    policy = record.get("policy") if isinstance(record.get("policy"), Mapping) else {}
    safety = record.get("safety_boundaries") if isinstance(record.get("safety_boundaries"), Mapping) else {}
    effect = record.get("decision_effect") if isinstance(record.get("decision_effect"), Mapping) else {}
    application_stub = record.get("application_stub") if isinstance(record.get("application_stub"), Mapping) else {}
    status = review.get("record_status")

    checks = {
        "version_matches_step264": record.get("version") == STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
        "staging_handoff_id_present": bool(record.get("staging_handoff_id")),
        "approval_packet_id_present": bool(record.get("approval_packet_id")),
        "validation_object_valid": validation.get("valid") is True,
        "review_recorded_matches_validation": review.get("recorded") is validation.get("valid"),
        "record_status_allowed": status in _ALLOWED_RECORD_STATUSES,
        "decision_allowed": review.get("review_decision") in set(policy.get("accepted_decisions") or []),
        "reviewer_present": bool(review.get("reviewer")),
        "rationale_present": bool(review.get("rationale")),
        "timestamp_utc_parseable": _parse_utc_timestamp(review.get("timestamp_utc")),
        "ready_record_requires_ready_source": status != "ready_for_disabled_pre_apply_review" or record.get("source_ready_for_pre_apply_review") is True,
        "ready_record_requires_candidate": status != "ready_for_disabled_pre_apply_review" or (record.get("candidate_available") is True and bool(record.get("production_candidate_profile"))),
        "policy_blocks_auto_apply": policy.get("auto_apply_reviewed_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_reviewed_profile_enabled") is False,
        "decision_effect_blocks_application": effect.get("runtime_profile_application_allowed") is False and effect.get("settings_profile_write_allowed") is False,
        "application_stub_disabled": application_stub.get("status") == "disabled_stub" and application_stub.get("apply_pre_apply_review_enabled") is False,
        "safety_blocks_runtime_mutation": safety.get("runtime_score_weights_mutated") is False,
        "safety_blocks_settings_mutation": safety.get("settings_score_weights_mutated") is False,
        "safety_blocks_live_trading": safety.get("live_trading_allowed") is False and safety.get("order_routing_enabled") is False,
        "missing_canonical_module_count_locked": safety.get("missing_canonical_module_count") == 2,
    }
    return {
        "schema_version": STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
        "valid": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
    }


def apply_step264_pre_apply_review_disabled_stub(record: Mapping[str, Any], cfg: Any = None) -> dict[str, Any]:
    """Disabled Step264 application surface.

    A valid READY record still cannot write score weights in this step.
    """
    original_weights = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else {}
    step263_stub = apply_step263_staging_handoff_disabled_stub(
        {
            "staging_handoff_id": record.get("staging_handoff_id"),
            "source": {"approval_packet_id": record.get("approval_packet_id")},
            "candidate": {"production_candidate_profile": record.get("production_candidate_profile")},
            "handoff": {"handoff_status": record.get("source_handoff_status")},
        },
        cfg,
    )
    review = record.get("pre_apply_review_record") if isinstance(record.get("pre_apply_review_record"), Mapping) else {}
    return {
        "status": "DISABLED_STUB",
        "reason": "Step264 pre-apply review is an audit record only; runtime score-weight application remains disabled.",
        "staging_handoff_id": record.get("staging_handoff_id"),
        "approval_packet_id": record.get("approval_packet_id"),
        "review_decision": review.get("review_decision"),
        "record_status": review.get("record_status"),
        "step263_stub_status": step263_stub.get("status"),
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
