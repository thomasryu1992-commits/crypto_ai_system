from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.utils.audit import file_metadata, is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical


STEP261_PROFILE_APPROVAL_PACKET_VERSION = "step261_researchsignal_profile_manual_approval_packet_v1"

DEFAULT_STEP261_APPROVAL_POLICY: dict[str, Any] = {
    "mode": "manual_approval_packet_review_only",
    "manual_approval_required": True,
    "approval_packet_write_enabled": True,
    "auto_apply_approved_profile": False,
    "runtime_score_weight_write_enabled": False,
    "settings_score_weight_write_enabled": False,
    "apply_approved_profile_enabled": False,
    "accepted_decisions": ["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"],
}

_ALLOWED_APPROVAL_STATUSES = {
    "pending_manual_approval",
    "no_candidate_available",
    "blocked_by_review_policy",
}


def _utc_now_iso() -> str:
    return utc_now_canonical()


def _get_cfg_path(cfg: Any, path: str, default: Any = None) -> Any:
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(path, default)
    return default


def resolve_step261_approval_policy(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve manual approval packet policy.

    This policy only controls whether a review packet may be written. It never
    enables profile application, config mutation, testnet routing, or live order
    submission.
    """
    policy = deepcopy(DEFAULT_STEP261_APPROVAL_POLICY)
    configured = _get_cfg_path(cfg, "research.calibration_approval", None)
    if isinstance(configured, Mapping):
        for key in policy:
            if key in configured:
                policy[key] = configured[key]
    if overrides:
        for key in policy:
            if key in overrides:
                policy[key] = overrides[key]

    # Hard locks: these cannot be enabled through config or overrides in Step261.
    policy["manual_approval_required"] = True
    policy["auto_apply_approved_profile"] = False
    policy["runtime_score_weight_write_enabled"] = False
    policy["settings_score_weight_write_enabled"] = False
    policy["apply_approved_profile_enabled"] = False
    return policy


def _stable_packet_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "step261_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _extract_review(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if "review" in source and isinstance(source.get("review"), Mapping):
        return source["review"]  # type: ignore[index]
    return source


def _profile_result_by_name(review: Mapping[str, Any], profile_name: str | None) -> Mapping[str, Any]:
    if not profile_name:
        return {}
    comparison = review.get("comparison") if isinstance(review.get("comparison"), Mapping) else {}
    for item in comparison.get("results", []) if isinstance(comparison, Mapping) else []:
        if isinstance(item, Mapping) and item.get("profile_name") == profile_name:
            return item
    return {}


def _profile_review_by_name(review: Mapping[str, Any], profile_name: str | None) -> Mapping[str, Any]:
    if not profile_name:
        return {}
    candidate_review = review.get("candidate_review") if isinstance(review.get("candidate_review"), Mapping) else {}
    for item in candidate_review.get("profile_reviews", []) if isinstance(candidate_review, Mapping) else []:
        if isinstance(item, Mapping) and item.get("profile_name") == profile_name:
            return item
    return {}


def build_step261_manual_approval_packet(
    step260_review_or_report: Mapping[str, Any],
    cfg: Any = None,
    *,
    operator_label: str = "manual_reviewer",
    notes: str = "",
    policy_overrides: Mapping[str, Any] | None = None,
    source_step_report_path: str | Path | None = None,
    source_step_report_sha256: str | None = None,
    feature_matrix_sha256: str | None = None,
    profile_candidate_sha256: str | None = None,
) -> dict[str, Any]:
    """Build a manual approval packet for a review-only candidate profile.

    The packet is an auditable handoff artifact. It is not an approval intake,
    does not apply the profile, and does not mutate runtime score weights.
    """
    review = _extract_review(step260_review_or_report)
    candidate_review = review.get("candidate_review") if isinstance(review.get("candidate_review"), Mapping) else {}
    candidate_profile = candidate_review.get("production_candidate_profile") if isinstance(candidate_review, Mapping) else None
    matrix_source_type = str(review.get("matrix_source_type") or "unknown")
    candidate_available = bool(candidate_profile) and matrix_source_type in {"stored_feature_store_matrix", "explicit_feature_store_matrix"}

    profile_result = _profile_result_by_name(review, str(candidate_profile) if candidate_profile else None)
    profile_review = _profile_review_by_name(review, str(candidate_profile) if candidate_profile else None)
    policy = resolve_step261_approval_policy(cfg, policy_overrides)
    source_report = file_metadata(source_step_report_path) if source_step_report_path else {"path": None, "exists": False, "sha256": None, "bytes": None}
    source_hash_matches = (source_step_report_sha256 is None or source_report.get("sha256") == source_step_report_sha256) if source_report.get("exists") is True else False
    candidate_payload_for_hash = {"profile": candidate_profile, "weights": dict(profile_result.get("weights") or {}) if isinstance(profile_result, Mapping) else {}}
    profile_candidate_sha = profile_candidate_sha256 or sha256_json(candidate_payload_for_hash)

    if candidate_available:
        approval_status = "pending_manual_approval"
        blocked_reasons: list[str] = []
    else:
        approval_status = "no_candidate_available"
        blocked_reasons = []
        if not candidate_profile:
            blocked_reasons.append("NO_PRODUCTION_CANDIDATE_PROFILE")
        if matrix_source_type not in {"stored_feature_store_matrix", "explicit_feature_store_matrix"}:
            blocked_reasons.append("REAL_FEATURE_STORE_MATRIX_REQUIRED")

    identity_payload = {
        "version": STEP261_PROFILE_APPROVAL_PACKET_VERSION,
        "source_step": 260,
        "source_review_version": review.get("version"),
        "matrix_source": review.get("matrix_source"),
        "matrix_source_type": matrix_source_type,
        "rows_evaluated": review.get("rows_evaluated"),
        "production_candidate_profile": candidate_profile,
        "candidate_review_score": profile_review.get("review_score") if isinstance(profile_review, Mapping) else None,
    }

    packet = {
        "step": 261,
        "version": STEP261_PROFILE_APPROVAL_PACKET_VERSION,
        "approval_packet_id": _stable_packet_id(identity_payload),
        "created_at_utc": _utc_now_iso(),
        "operator_label": str(operator_label),
        "notes": str(notes),
        "source": {
            "source_step": 260,
            "source_review_version": review.get("version"),
            "matrix_source": review.get("matrix_source"),
            "matrix_source_type": matrix_source_type,
            "rows_evaluated": int(review.get("rows_evaluated") or 0),
            "candidate_selection_reason": candidate_review.get("selection_reason") if isinstance(candidate_review, Mapping) else None,
            "source_step_report_path": source_report.get("path"),
            "source_step_report_sha256": source_report.get("sha256"),
            "source_step_report_bytes": source_report.get("bytes"),
            "source_step_report_exists": source_report.get("exists"),
            "source_step_report_hash_matches": source_hash_matches,
            "feature_matrix_sha256": feature_matrix_sha256 or review.get("feature_matrix_sha256"),
            "profile_candidate_sha256": profile_candidate_sha,
        },
        "candidate": {
            "candidate_available": candidate_available,
            "production_candidate_profile": candidate_profile,
            "candidate_weights": dict(profile_result.get("weights") or {}) if isinstance(profile_result, Mapping) else {},
            "candidate_review_status": profile_review.get("status") if isinstance(profile_review, Mapping) else None,
            "candidate_review_score": profile_review.get("review_score") if isinstance(profile_review, Mapping) else None,
            "permission_distribution": dict(profile_result.get("permission_distribution") or {}) if isinstance(profile_result, Mapping) else {},
            "entry_allowed_ratio": profile_result.get("entry_allowed_ratio") if isinstance(profile_result, Mapping) else None,
            "blocked_ratio": profile_result.get("blocked_ratio") if isinstance(profile_result, Mapping) else None,
            "reduced_ratio": profile_result.get("reduced_ratio") if isinstance(profile_result, Mapping) else None,
            "blocked_reasons": blocked_reasons,
        },
        "approval": {
            "approval_status": approval_status,
            "manual_approval_required": True,
            "approval_recorded": False,
            "approval_decision": None,
            "approval_recorded_at_utc": None,
            "approval_recorded_by": None,
            "approval_schema": {
                "required_fields": ["approval_packet_id", "approval_decision", "approver", "rationale", "timestamp_utc"],
                "accepted_decisions": list(policy.get("accepted_decisions") or DEFAULT_STEP261_APPROVAL_POLICY["accepted_decisions"]),
                "decision_note": "APPROVE_FOR_REVIEW_ONLY_STAGING is not runtime application approval and cannot mutate score_weights in Step261.",
            },
        },
        "policy": policy,
        "application_stub": {
            "status": "disabled_stub",
            "apply_approved_profile_enabled": False,
            "reason": "Step261 creates a manual approval packet only. Runtime score-weight application is deferred.",
        },
        "approval_packet_sha256": None,
        "safety_boundaries": {
            "review_only": True,
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
    packet["approval_packet_sha256"] = sha256_json({k: v for k, v in packet.items() if k != "approval_packet_sha256"})
    return packet


def validate_step261_approval_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Validate packet shape and non-application safety locks."""
    approval = packet.get("approval") if isinstance(packet.get("approval"), Mapping) else {}
    candidate = packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}
    safety = packet.get("safety_boundaries") if isinstance(packet.get("safety_boundaries"), Mapping) else {}
    policy = packet.get("policy") if isinstance(packet.get("policy"), Mapping) else {}
    source = packet.get("source") if isinstance(packet.get("source"), Mapping) else {}
    application_stub = packet.get("application_stub") if isinstance(packet.get("application_stub"), Mapping) else {}

    checks = {
        "version_matches_step261": packet.get("version") == STEP261_PROFILE_APPROVAL_PACKET_VERSION,
        "approval_packet_id_present": bool(packet.get("approval_packet_id")),
        "created_at_utc_canonical": is_canonical_utc_timestamp(packet.get("created_at_utc")),
        "approval_packet_sha256_valid": packet.get("approval_packet_sha256") == sha256_json({k: v for k, v in packet.items() if k != "approval_packet_sha256"}),
        "approval_status_allowed": approval.get("approval_status") in _ALLOWED_APPROVAL_STATUSES,
        "manual_approval_required": approval.get("manual_approval_required") is True,
        "approval_not_recorded": approval.get("approval_recorded") is False,
        "candidate_shape_present": isinstance(candidate, Mapping) and "production_candidate_profile" in candidate,
        "source_report_declared": bool(source.get("source_step_report_path")),
        "source_report_present": source.get("source_step_report_exists") is True,
        "source_report_hash_present": bool(source.get("source_step_report_sha256")),
        "source_report_not_missing_when_declared": source.get("source_step_report_exists") is not False,
        "source_report_hash_matches_when_declared": source.get("source_step_report_hash_matches") is True,
        "application_stub_disabled": application_stub.get("status") == "disabled_stub" and application_stub.get("apply_approved_profile_enabled") is False,
        "policy_blocks_auto_apply": policy.get("auto_apply_approved_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply_stub": policy.get("apply_approved_profile_enabled") is False,
        "safety_blocks_runtime_mutation": safety.get("runtime_score_weights_mutated") is False,
        "safety_blocks_settings_mutation": safety.get("settings_score_weights_mutated") is False,
        "safety_blocks_live_trading": safety.get("live_trading_allowed") is False and safety.get("order_routing_enabled") is False,
        "missing_canonical_module_count_locked": safety.get("missing_canonical_module_count") == 2,
    }
    return {
        "schema_version": STEP261_PROFILE_APPROVAL_PACKET_VERSION,
        "valid": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
    }


def apply_step261_approved_profile_disabled_stub(packet: Mapping[str, Any], cfg: Any = None) -> dict[str, Any]:
    """Disabled application surface for Step261.

    This intentionally does not inspect approval decisions for execution and does
    not write research.score_weights. It exists so tests can lock the boundary
    before a future explicit apply stage is designed.
    """
    original_weights = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else {}
    return {
        "status": "DISABLED_STUB",
        "reason": "Step261 approval packets are review artifacts only; runtime profile application is deferred.",
        "approval_packet_id": packet.get("approval_packet_id"),
        "production_candidate_profile": (packet.get("candidate") or {}).get("production_candidate_profile") if isinstance(packet.get("candidate"), Mapping) else None,
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
