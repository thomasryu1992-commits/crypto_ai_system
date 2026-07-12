from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from crypto_ai_system.research.research_signal_profile_pre_apply_review import (
    STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
    apply_step264_pre_apply_review_disabled_stub,
    validate_step264_pre_apply_review_record,
)


STEP265_PROFILE_APPLY_DRY_RUN_VERSION = "step265_researchsignal_profile_disabled_apply_candidate_dry_run_v1"

DEFAULT_STEP265_APPLY_DRY_RUN_POLICY: dict[str, Any] = {
    "mode": "disabled_apply_candidate_dry_run_packet",
    "dry_run_packet_write_enabled": True,
    "manual_apply_approval_required": True,
    "auto_apply_candidate_profile": False,
    "runtime_score_weight_write_enabled": False,
    "settings_score_weight_write_enabled": False,
    "apply_candidate_profile_enabled": False,
    "mutation_plan_write_enabled": True,
    "diff_required": True,
    "accepted_source_record_statuses": ["ready_for_disabled_pre_apply_review"],
}

_READY_SOURCE_STATUS = "ready_for_disabled_pre_apply_review"
_READY_DRY_RUN_STATUS = "ready_disabled_apply_dry_run"
_BLOCKED_DRY_RUN_STATUS = "blocked_by_pre_apply_review"
_INVALID_DRY_RUN_STATUS = "invalid_source_pre_apply_review"
_ALLOWED_DRY_RUN_STATUSES = {_READY_DRY_RUN_STATUS, _BLOCKED_DRY_RUN_STATUS, _INVALID_DRY_RUN_STATUS}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_cfg_path(cfg: Any, path: str, default: Any = None) -> Any:
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(path, default)
    return default


def _extract_pre_apply_record(source: Mapping[str, Any]) -> Mapping[str, Any]:
    if "pre_apply_review_record" in source and isinstance(source.get("pre_apply_review_record"), Mapping):
        return source["pre_apply_review_record"]  # type: ignore[index]
    return source


def _stable_dry_run_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "step265_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def resolve_step265_apply_dry_run_policy(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Step265 dry-run policy with hard non-mutation locks.

    Step265 may create a candidate/current-settings diff and a hypothetical
    mutation plan. It may not write settings, mutate runtime weights, or enable
    execution.
    """
    policy = deepcopy(DEFAULT_STEP265_APPLY_DRY_RUN_POLICY)
    configured = _get_cfg_path(cfg, "research.calibration_apply_dry_run", None)
    if isinstance(configured, Mapping):
        for key in policy:
            if key in configured:
                policy[key] = configured[key]
    if overrides:
        for key in policy:
            if key in overrides:
                policy[key] = overrides[key]

    # Hard locks: config/override values cannot turn dry-run into apply.
    policy["manual_apply_approval_required"] = True
    policy["auto_apply_candidate_profile"] = False
    policy["runtime_score_weight_write_enabled"] = False
    policy["settings_score_weight_write_enabled"] = False
    policy["apply_candidate_profile_enabled"] = False
    policy["mutation_plan_write_enabled"] = True
    policy["diff_required"] = True

    accepted = policy.get("accepted_source_record_statuses")
    if not isinstance(accepted, list) or not accepted:
        policy["accepted_source_record_statuses"] = list(DEFAULT_STEP265_APPLY_DRY_RUN_POLICY["accepted_source_record_statuses"])
    return policy


def _review_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return record.get("pre_apply_review_record") if isinstance(record.get("pre_apply_review_record"), Mapping) else {}


def _current_score_weights(cfg: Any) -> dict[str, float]:
    weights = _get_cfg_path(cfg, "research.score_weights", {}) or {}
    return {str(k): float(v) for k, v in dict(weights).items()}


def _candidate_weights_from_cfg(profile_name: Any, cfg: Any) -> tuple[dict[str, float], str, list[str]]:
    name = str(profile_name or "").strip()
    if not name:
        return {}, "missing_profile_name", ["PRODUCTION_CANDIDATE_PROFILE_MISSING"]
    profiles = _get_cfg_path(cfg, "research.score_weight_profiles", {}) or {}
    if not isinstance(profiles, Mapping) or name not in profiles:
        return {}, "missing_config_profile", ["CANDIDATE_PROFILE_WEIGHTS_NOT_FOUND_IN_CONFIG"]
    profile = profiles.get(name)
    if not isinstance(profile, Mapping) or not profile:
        return {}, "empty_config_profile", ["CANDIDATE_PROFILE_WEIGHTS_EMPTY"]
    try:
        weights = {str(k): float(v) for k, v in dict(profile).items()}
    except (TypeError, ValueError):
        return {}, "invalid_config_profile", ["CANDIDATE_PROFILE_WEIGHTS_NOT_NUMERIC"]
    return weights, "config.research.score_weight_profiles", []


def build_score_weight_diff(current_weights: Mapping[str, Any], candidate_weights: Mapping[str, Any]) -> dict[str, Any]:
    current = {str(k): float(v) for k, v in dict(current_weights).items()}
    candidate = {str(k): float(v) for k, v in dict(candidate_weights).items()}
    keys = sorted(set(current) | set(candidate))
    details: dict[str, dict[str, Any]] = {}
    added: list[str] = []
    removed: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []

    for key in keys:
        before_present = key in current
        after_present = key in candidate
        before = current.get(key)
        after = candidate.get(key)
        if before_present and not after_present:
            status = "removed"
            removed.append(key)
            delta = None
        elif after_present and not before_present:
            status = "added"
            added.append(key)
            delta = None
        else:
            delta = float(after) - float(before)  # type: ignore[arg-type]
            if abs(delta) <= 1e-12:
                status = "unchanged"
                unchanged.append(key)
            else:
                status = "changed"
                changed.append(key)
        details[key] = {
            "current": before,
            "candidate": after,
            "delta": delta,
            "status": status,
        }

    current_sum = sum(current.values())
    candidate_sum = sum(candidate.values())
    return {
        "current_weight_sum": current_sum,
        "candidate_weight_sum": candidate_sum,
        "sum_delta": candidate_sum - current_sum,
        "keys_total": len(keys),
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "changed_count": len(changed),
        "added_count": len(added),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
        "has_diff": bool(added or removed or changed),
        "details": details,
    }


def _source_status(record: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[str, list[str]]:
    validation = validate_step264_pre_apply_review_record(record)
    review = _review_record(record)
    reasons: list[str] = []
    accepted_statuses = set(policy.get("accepted_source_record_statuses") or [])
    record_status = review.get("record_status")

    if validation.get("valid") is not True:
        reasons.append("SOURCE_STEP264_PRE_APPLY_REVIEW_VALIDATION_FAILED")
    if record.get("version") != STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION:
        reasons.append("SOURCE_STEP264_VERSION_MISMATCH")
    if record_status not in accepted_statuses:
        reasons.append("SOURCE_RECORD_STATUS_NOT_READY_FOR_DISABLED_PRE_APPLY_REVIEW")
    if record_status != _READY_SOURCE_STATUS:
        reasons.append("READY_PRE_APPLY_REVIEW_RECORD_REQUIRED")
    if review.get("recorded") is not True:
        reasons.append("SOURCE_PRE_APPLY_REVIEW_NOT_RECORDED")
    if record.get("candidate_available") is not True:
        reasons.append("CANDIDATE_PROFILE_NOT_AVAILABLE")
    if not record.get("production_candidate_profile"):
        reasons.append("PRODUCTION_CANDIDATE_PROFILE_MISSING")

    if validation.get("valid") is not True:
        return _INVALID_DRY_RUN_STATUS, reasons
    if reasons:
        return _BLOCKED_DRY_RUN_STATUS, reasons
    return _READY_DRY_RUN_STATUS, ["DISABLED_APPLY_CANDIDATE_DRY_RUN_READY"]


def build_step265_disabled_apply_candidate_dry_run_packet(
    step264_pre_apply_record_or_report: Mapping[str, Any],
    cfg: Any = None,
    *,
    operator_label: str = "manual_reviewer",
    notes: str = "",
    timestamp_utc: str | None = None,
    policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a disabled apply-candidate dry-run packet from a Step264 record.

    The packet computes the candidate/current settings diff and a hypothetical
    mutation plan. It deliberately cannot write those weights anywhere.
    """
    record = _extract_pre_apply_record(step264_pre_apply_record_or_report)
    policy = resolve_step265_apply_dry_run_policy(cfg, policy_overrides)
    current_weights = _current_score_weights(cfg)
    dry_run_status, source_reasons = _source_status(record, policy)
    profile_name = record.get("production_candidate_profile")
    candidate_weights, candidate_weights_source, candidate_weight_reasons = _candidate_weights_from_cfg(profile_name, cfg)
    diff = build_score_weight_diff(current_weights, candidate_weights)
    review = _review_record(record)
    source_validation = validate_step264_pre_apply_review_record(record)

    blocked_reasons = list(source_reasons)
    if dry_run_status == _READY_DRY_RUN_STATUS and candidate_weight_reasons:
        dry_run_status = _BLOCKED_DRY_RUN_STATUS
        blocked_reasons.extend(candidate_weight_reasons)
    elif candidate_weight_reasons:
        blocked_reasons.extend(candidate_weight_reasons)

    mutation_operations = []
    for key in diff.get("added", []):
        mutation_operations.append({"operation": "would_add_weight", "key": key, "value": candidate_weights.get(key), "enabled": False})
    for key in diff.get("removed", []):
        mutation_operations.append({"operation": "would_remove_weight", "key": key, "current": current_weights.get(key), "enabled": False})
    for key in diff.get("changed", []):
        mutation_operations.append({
            "operation": "would_update_weight",
            "key": key,
            "current": current_weights.get(key),
            "candidate": candidate_weights.get(key),
            "delta": diff["details"][key]["delta"],
            "enabled": False,
        })

    identity_payload = {
        "version": STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
        "source_step": 264,
        "staging_handoff_id": record.get("staging_handoff_id"),
        "approval_packet_id": record.get("approval_packet_id"),
        "record_status": review.get("record_status"),
        "production_candidate_profile": profile_name,
        "dry_run_status": dry_run_status,
    }
    packet = {
        "step": 265,
        "version": STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
        "apply_dry_run_id": _stable_dry_run_id(identity_payload),
        "created_at_utc": _utc_now_iso(),
        "operator_label": str(operator_label),
        "notes": str(notes),
        "timestamp_utc": timestamp_utc or _utc_now_iso(),
        "source": {
            "source_step": 264,
            "source_version": record.get("version"),
            "staging_handoff_id": record.get("staging_handoff_id"),
            "approval_packet_id": record.get("approval_packet_id"),
            "review_decision": review.get("review_decision"),
            "canonical_review_decision": review.get("canonical_review_decision"),
            "record_status": review.get("record_status"),
            "recorded": review.get("recorded") is True,
            "source_validation_valid": source_validation.get("valid") is True,
        },
        "candidate": {
            "candidate_available": record.get("candidate_available") is True,
            "production_candidate_profile": profile_name,
            "candidate_weights": candidate_weights,
            "candidate_weights_source": candidate_weights_source,
            "candidate_weights_present": bool(candidate_weights),
            "candidate_weights_reload_required_before_future_apply": not bool(candidate_weights),
            "candidate_weight_reasons": candidate_weight_reasons,
        },
        "current_settings": {
            "score_weights_path": "research.score_weights",
            "score_weights": current_weights,
        },
        "diff": diff,
        "dry_run": {
            "dry_run_status": dry_run_status,
            "ready_for_disabled_apply_dry_run": dry_run_status == _READY_DRY_RUN_STATUS,
            "blocked_reasons": blocked_reasons,
            "mutation_plan_created": True,
            "mutation_plan_enabled": False,
            "mutation_plan_status": "disabled_dry_run_only" if dry_run_status == _READY_DRY_RUN_STATUS else "blocked_or_invalid_source",
            "score_weight_write_allowed": False,
            "settings_write_allowed": False,
            "runtime_apply_allowed": False,
        },
        "mutation_plan": {
            "plan_type": "score_weight_profile_apply_candidate",
            "plan_status": "disabled_dry_run_only" if dry_run_status == _READY_DRY_RUN_STATUS else "blocked_or_invalid_source",
            "operations": mutation_operations,
            "operation_count": len(mutation_operations),
            "would_write_path": "research.score_weights",
            "write_enabled": False,
            "apply_enabled": False,
            "requires_future_manual_enablement_step": True,
        },
        "policy": policy,
        "application_stub": {
            "status": "disabled_stub",
            "apply_candidate_profile_enabled": False,
            "reason": "Step265 creates a dry-run diff and disabled mutation plan only. Score-weight writes remain disabled.",
        },
        "safety_boundaries": {
            "review_only": True,
            "dry_run_only": True,
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


def validate_step265_disabled_apply_candidate_dry_run_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    dry_run = packet.get("dry_run") if isinstance(packet.get("dry_run"), Mapping) else {}
    candidate = packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}
    current_settings = packet.get("current_settings") if isinstance(packet.get("current_settings"), Mapping) else {}
    diff = packet.get("diff") if isinstance(packet.get("diff"), Mapping) else {}
    mutation_plan = packet.get("mutation_plan") if isinstance(packet.get("mutation_plan"), Mapping) else {}
    policy = packet.get("policy") if isinstance(packet.get("policy"), Mapping) else {}
    stub = packet.get("application_stub") if isinstance(packet.get("application_stub"), Mapping) else {}
    safety = packet.get("safety_boundaries") if isinstance(packet.get("safety_boundaries"), Mapping) else {}
    source = packet.get("source") if isinstance(packet.get("source"), Mapping) else {}
    status = dry_run.get("dry_run_status")

    checks = {
        "version_matches_step265": packet.get("version") == STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
        "apply_dry_run_id_present": bool(packet.get("apply_dry_run_id")),
        "source_step264_version_matches": source.get("source_version") == STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
        "dry_run_status_allowed": status in _ALLOWED_DRY_RUN_STATUSES,
        "ready_requires_ready_step264_source": status != _READY_DRY_RUN_STATUS or source.get("record_status") == _READY_SOURCE_STATUS,
        "candidate_profile_present_when_ready": status != _READY_DRY_RUN_STATUS or bool(candidate.get("production_candidate_profile")),
        "candidate_weights_present_when_ready": status != _READY_DRY_RUN_STATUS or bool(candidate.get("candidate_weights")),
        "current_score_weights_present": bool(current_settings.get("score_weights")),
        "diff_shape_present": isinstance(diff.get("details"), Mapping) and isinstance(diff.get("has_diff"), bool),
        "mutation_plan_created_but_disabled": mutation_plan.get("write_enabled") is False and mutation_plan.get("apply_enabled") is False,
        "mutation_operations_disabled": all((op.get("enabled") is False) for op in mutation_plan.get("operations", []) if isinstance(op, Mapping)),
        "policy_blocks_auto_apply": policy.get("auto_apply_candidate_profile") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_apply": policy.get("apply_candidate_profile_enabled") is False,
        "application_stub_disabled": stub.get("status") == "disabled_stub" and stub.get("apply_candidate_profile_enabled") is False,
        "safety_blocks_runtime_mutation": safety.get("runtime_score_weights_mutated") is False,
        "safety_blocks_settings_mutation": safety.get("settings_score_weights_mutated") is False,
        "safety_blocks_live_trading": safety.get("live_trading_allowed") is False and safety.get("order_routing_enabled") is False,
        "missing_canonical_module_count_locked": safety.get("missing_canonical_module_count") == 2,
    }
    return {
        "schema_version": STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
        "valid": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
    }


def apply_step265_disabled_apply_candidate_dry_run_stub(packet: Mapping[str, Any], cfg: Any = None) -> dict[str, Any]:
    """Disabled Step265 apply surface.

    Even a ready dry-run packet is not permitted to mutate runtime or settings.
    """
    original_weights = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else {}
    step264_stub = apply_step264_pre_apply_review_disabled_stub(
        {
            "staging_handoff_id": (packet.get("source") or {}).get("staging_handoff_id") if isinstance(packet.get("source"), Mapping) else None,
            "approval_packet_id": (packet.get("source") or {}).get("approval_packet_id") if isinstance(packet.get("source"), Mapping) else None,
            "production_candidate_profile": (packet.get("candidate") or {}).get("production_candidate_profile") if isinstance(packet.get("candidate"), Mapping) else None,
            "source_handoff_status": "ready_for_pre_apply_review",
            "pre_apply_review_record": {
                "review_decision": (packet.get("source") or {}).get("review_decision") if isinstance(packet.get("source"), Mapping) else None,
                "record_status": (packet.get("source") or {}).get("record_status") if isinstance(packet.get("source"), Mapping) else None,
            },
        },
        cfg,
    )
    return {
        "status": "DISABLED_STUB",
        "reason": "Step265 is dry-run only; score-weight mutation and settings writes remain disabled.",
        "apply_dry_run_id": packet.get("apply_dry_run_id"),
        "dry_run_status": (packet.get("dry_run") or {}).get("dry_run_status") if isinstance(packet.get("dry_run"), Mapping) else None,
        "production_candidate_profile": (packet.get("candidate") or {}).get("production_candidate_profile") if isinstance(packet.get("candidate"), Mapping) else None,
        "step264_stub_status": step264_stub.get("status"),
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
