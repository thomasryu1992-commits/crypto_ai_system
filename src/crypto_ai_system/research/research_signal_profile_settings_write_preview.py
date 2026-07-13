from __future__ import annotations

import difflib
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_bytes, utc_now_canonical
from crypto_ai_system.research.research_signal_profile_final_apply_approval import (
    STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
    validate_step266_final_manual_apply_approval_record,
)


STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION = "step267_researchsignal_profile_disabled_settings_write_preview_export_v1"

_READY_PREVIEW_STATUS = "ready_disabled_settings_write_preview"
_BLOCKED_PREVIEW_STATUS = "blocked_by_final_apply_approval_record"
_INVALID_PREVIEW_STATUS = "invalid_source_final_apply_approval_record"
_APPROVED_SOURCE_STATUS = "approved_disabled_apply_dry_run"

DEFAULT_STEP267_SETTINGS_WRITE_PREVIEW_POLICY: dict[str, Any] = {
    "mode": "disabled_settings_write_preview_export_only",
    "settings_write_preview_export_enabled": True,
    "manual_settings_write_review_required": True,
    "auto_apply_approved_profile": False,
    "runtime_score_weight_write_enabled": False,
    "settings_score_weight_write_enabled": False,
    "config_write_enabled": False,
    "settings_file_write_enabled": False,
    "apply_preview_enabled": False,
    "accepted_source_record_statuses": [_APPROVED_SOURCE_STATUS],
    "target_yaml_path": "research.score_weights",
    "target_settings_file": "config/settings.yaml",
}


def _utc_now_iso() -> str:
    return utc_now_canonical()


def _get_cfg_path(cfg: Any, path: str, default: Any = None) -> Any:
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(path, default)
    return default


def _settings_dict(cfg: Any) -> dict[str, Any]:
    settings = getattr(cfg, "settings", None)
    if isinstance(settings, dict):
        return settings
    return {}


def _cfg_root(cfg: Any) -> Path | None:
    root = getattr(cfg, "root", None)
    if root is None:
        return None
    try:
        return Path(root).resolve()
    except TypeError:
        return None


def _extract_final_apply_record(source: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = source.get("final_apply_approval_record")
    if isinstance(nested, Mapping) and nested.get("step") == 266:
        return nested
    if source.get("step") == 266 and isinstance(source.get("final_apply_approval_record"), Mapping):
        return source
    return source


def _stable_preview_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "step267_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _coerce_weights(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): float(v) for k, v in dict(value).items()}


def resolve_step267_settings_write_preview_policy(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Step267 preview policy with hard config-write and score-mutation locks."""
    policy = deepcopy(DEFAULT_STEP267_SETTINGS_WRITE_PREVIEW_POLICY)
    configured = _get_cfg_path(cfg, "research.calibration_settings_write_preview", None)
    if isinstance(configured, Mapping):
        for key in policy:
            if key in configured:
                policy[key] = configured[key]
    if overrides:
        for key in policy:
            if key in overrides:
                policy[key] = overrides[key]

    # Hard locks: Step267 can render/export a preview only. It never writes settings.
    policy["settings_write_preview_export_enabled"] = True
    policy["manual_settings_write_review_required"] = True
    policy["auto_apply_approved_profile"] = False
    policy["runtime_score_weight_write_enabled"] = False
    policy["settings_score_weight_write_enabled"] = False
    policy["config_write_enabled"] = False
    policy["settings_file_write_enabled"] = False
    policy["apply_preview_enabled"] = False
    policy["target_yaml_path"] = "research.score_weights"
    policy["target_settings_file"] = "config/settings.yaml"

    statuses = policy.get("accepted_source_record_statuses")
    if not isinstance(statuses, list) or not statuses:
        policy["accepted_source_record_statuses"] = [_APPROVED_SOURCE_STATUS]
    return policy


def _source_record_status(record: Mapping[str, Any]) -> str:
    approval = record.get("final_apply_approval_record") if isinstance(record.get("final_apply_approval_record"), Mapping) else {}
    return str(approval.get("record_status") or "")


def _source_decision_effect(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return record.get("decision_effect") if isinstance(record.get("decision_effect"), Mapping) else {}


def _source_safety(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return record.get("safety_boundaries") if isinstance(record.get("safety_boundaries"), Mapping) else {}


def _source_status(record: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    validation = validate_step266_final_manual_apply_approval_record(record)
    status = _source_record_status(record)
    effect = _source_decision_effect(record)
    safety = _source_safety(record)
    accepted_statuses = set(policy.get("accepted_source_record_statuses") or [])
    reasons: list[str] = []

    if validation.get("valid") is not True:
        reasons.append("SOURCE_STEP266_FINAL_APPLY_APPROVAL_VALIDATION_FAILED")
    if record.get("version") != STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION:
        reasons.append("SOURCE_STEP266_VERSION_MISMATCH")
    if status not in accepted_statuses:
        reasons.append("SOURCE_RECORD_STATUS_NOT_APPROVED_DISABLED_DRY_RUN")
    if effect.get("disabled_dry_run_final_approval_recorded") is not True:
        reasons.append("SOURCE_FINAL_APPROVAL_NOT_RECORDED_FOR_DISABLED_DRY_RUN")
    if record.get("candidate_available") is not True:
        reasons.append("CANDIDATE_PROFILE_NOT_AVAILABLE")
    if not record.get("production_candidate_profile"):
        reasons.append("PRODUCTION_CANDIDATE_PROFILE_MISSING")
    if record.get("candidate_weights_present") is not True:
        reasons.append("CANDIDATE_WEIGHTS_NOT_PRESENT_IN_SOURCE")
    if record.get("mutation_plan_write_enabled") is not False:
        reasons.append("SOURCE_MUTATION_PLAN_WRITE_MUST_BE_DISABLED")
    if record.get("mutation_plan_apply_enabled") is not False:
        reasons.append("SOURCE_MUTATION_PLAN_APPLY_MUST_BE_DISABLED")
    if safety.get("external_order_submission_performed") is not False:
        reasons.append("SOURCE_EXTERNAL_ORDER_SUBMISSION_MUST_BE_FALSE")
    if safety.get("live_trading_allowed") is not False:
        reasons.append("SOURCE_LIVE_TRADING_MUST_BE_FALSE")

    if validation.get("valid") is not True:
        return _INVALID_PREVIEW_STATUS, reasons, validation
    if reasons:
        return _BLOCKED_PREVIEW_STATUS, reasons, validation
    return _READY_PREVIEW_STATUS, ["DISABLED_SETTINGS_WRITE_PREVIEW_READY"], validation


def _candidate_weights_from_cfg(profile_name: Any, cfg: Any) -> tuple[dict[str, float], str, list[str]]:
    profile_key = str(profile_name or "").strip()
    if not profile_key:
        return {}, "missing_profile_name", ["PRODUCTION_CANDIDATE_PROFILE_MISSING"]
    profiles = _get_cfg_path(cfg, "research.score_weight_profiles", {}) or {}
    if not isinstance(profiles, Mapping):
        return {}, "invalid_config_profile_container", ["SCORE_WEIGHT_PROFILES_CONFIG_INVALID"]
    profile = profiles.get(profile_key)
    if not isinstance(profile, Mapping):
        return {}, "missing_config_profile", ["CANDIDATE_PROFILE_WEIGHTS_NOT_FOUND_IN_CONFIG"]
    try:
        return _coerce_weights(profile), "config.research.score_weight_profiles", []
    except (TypeError, ValueError):
        return {}, "invalid_config_profile", ["CANDIDATE_PROFILE_WEIGHTS_NOT_NUMERIC"]


def _current_weights(cfg: Any) -> dict[str, float]:
    try:
        return _coerce_weights(_get_cfg_path(cfg, "research.score_weights", {}) or {})
    except (TypeError, ValueError):
        return {}


def _set_nested(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = deepcopy(data)
    node: Any = out
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = deepcopy(value)
    return out


def _dump_yaml(data: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True)


def _read_current_settings_yaml(cfg: Any, settings_path: Path | None = None) -> tuple[str, str, bool]:
    root = _cfg_root(cfg)
    if settings_path is None:
        settings_path = (root / "config/settings.yaml") if root else Path("config/settings.yaml")
    exists = settings_path.exists()
    if exists:
        # Step268: preview is based only on actual config/settings.yaml bytes.
        return settings_path.read_text(encoding="utf-8"), str(settings_path), True
    # Fail closed. Do not reconstruct settings.yaml from cfg object.
    return "", str(settings_path), False


def _build_settings_yaml_artifact(cfg: Any, candidate_weights: Mapping[str, float], settings_path: Path | None = None) -> dict[str, Any]:
    current_yaml, resolved_path, exists = _read_current_settings_yaml(cfg, settings_path)
    current_settings = _settings_dict(cfg)
    candidate_settings = _set_nested(current_settings, "research.score_weights", dict(candidate_weights))
    if exists:
        candidate_yaml = _dump_yaml(candidate_settings)
        diff_lines = list(difflib.unified_diff(
            current_yaml.splitlines(keepends=True),
            candidate_yaml.splitlines(keepends=True),
            fromfile="config/settings.yaml.current",
            tofile="config/settings.yaml.preview_candidate",
            lineterm="",
        ))
    else:
        candidate_yaml = ""
        diff_lines = []
    return {
        "target_settings_file": "config/settings.yaml",
        "resolved_settings_path": resolved_path,
        "settings_file_exists": exists,
        "target_yaml_path": "research.score_weights",
        "operation": "replace_mapping_preview_only",
        "current_settings_yaml_sha256": _sha256_text(current_yaml) if exists else None,
        "candidate_settings_yaml_sha256": _sha256_text(candidate_yaml) if exists else None,
        "fail_closed_reason": None if exists else "TARGET_SETTINGS_FILE_MISSING_FAIL_CLOSED",
        "current_settings_yaml_bytes": len(current_yaml.encode("utf-8")),
        "candidate_settings_yaml_bytes": len(candidate_yaml.encode("utf-8")),
        "unified_diff": "".join(diff_lines),
        "candidate_settings_yaml": candidate_yaml,
    }


def _weight_diff(current_weights: Mapping[str, float], candidate_weights: Mapping[str, float]) -> dict[str, Any]:
    keys = sorted(set(current_weights) | set(candidate_weights))
    added: list[str] = []
    removed: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []
    details: dict[str, dict[str, Any]] = {}
    for key in keys:
        before_present = key in current_weights
        after_present = key in candidate_weights
        before = current_weights.get(key)
        after = candidate_weights.get(key)
        if before_present and not after_present:
            status = "removed"
            delta = None
            removed.append(key)
        elif after_present and not before_present:
            status = "added"
            delta = None
            added.append(key)
        else:
            delta = float(after) - float(before)  # type: ignore[arg-type]
            if abs(delta) <= 1e-12:
                status = "unchanged"
                unchanged.append(key)
            else:
                status = "changed"
                changed.append(key)
        details[key] = {"current": before, "candidate": after, "delta": delta, "status": status}
    current_sum = sum(float(v) for v in current_weights.values())
    candidate_sum = sum(float(v) for v in candidate_weights.values())
    return {
        "current_weight_sum": current_sum,
        "candidate_weight_sum": candidate_sum,
        "sum_delta": candidate_sum - current_sum,
        "keys_total": len(keys),
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "has_diff": bool(added or removed or changed),
        "details": details,
    }


def build_step267_disabled_settings_write_preview_packet(
    step266_final_approval_or_report: Mapping[str, Any],
    cfg: Any,
    *,
    operator_label: str = "manual_settings_write_preview_reviewer",
    notes: str = "",
    timestamp_utc: str | None = None,
    settings_path: str | Path | None = None,
    policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a disabled settings-write preview/export packet.

    The packet renders the exact candidate settings.yaml preview and unified diff
    that would be used by a future write stage. Step267 never writes that file,
    mutates runtime score weights, or enables execution.
    """
    record = _extract_final_apply_record(step266_final_approval_or_report)
    policy = resolve_step267_settings_write_preview_policy(cfg, policy_overrides)
    timestamp = timestamp_utc or _utc_now_iso()
    preview_status, source_reasons, source_validation = _source_status(record, policy)
    profile_name = record.get("production_candidate_profile")
    candidate_weights, candidate_weights_source, candidate_weight_reasons = _candidate_weights_from_cfg(profile_name, cfg)
    current_weights = _current_weights(cfg)
    blocked_reasons = list(source_reasons)

    if candidate_weight_reasons:
        blocked_reasons.extend(candidate_weight_reasons)
        if preview_status == _READY_PREVIEW_STATUS:
            preview_status = _BLOCKED_PREVIEW_STATUS

    diff = _weight_diff(current_weights, candidate_weights)
    artifact = _build_settings_yaml_artifact(cfg, candidate_weights, Path(settings_path) if settings_path else None)
    if artifact.get("settings_file_exists") is not True:
        blocked_reasons.append("TARGET_SETTINGS_FILE_MISSING_FAIL_CLOSED")
        if preview_status == _READY_PREVIEW_STATUS:
            preview_status = _BLOCKED_PREVIEW_STATUS
    ready = preview_status == _READY_PREVIEW_STATUS and not candidate_weight_reasons and artifact.get("settings_file_exists") is True
    identity_payload = {
        "version": STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION,
        "source_step": 266,
        "final_apply_approval_id": record.get("final_apply_approval_id"),
        "production_candidate_profile": profile_name,
        "preview_status": preview_status,
        "candidate_settings_yaml_sha256": artifact["candidate_settings_yaml_sha256"],
    }
    packet = {
        "step": 267,
        "version": STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION,
        "created_at_utc": _utc_now_iso(),
        "settings_write_preview_id": _stable_preview_id(identity_payload),
        "source_final_apply_approval_id": record.get("final_apply_approval_id"),
        "source_final_apply_approval_version": record.get("version"),
        "source_record_status": _source_record_status(record),
        "production_candidate_profile": profile_name,
        "candidate_available": record.get("candidate_available") is True,
        "candidate_weights_present": bool(candidate_weights),
        "preview": {
            "preview_status": preview_status,
            "ready_for_disabled_settings_write_preview": ready,
            "blocked_reasons": blocked_reasons,
            "operator_label": str(operator_label or ""),
            "notes": str(notes or ""),
            "timestamp_utc": timestamp,
            "timestamp_utc_canonical": is_canonical_utc_timestamp(timestamp),
        },
        "source": {
            "step266_validation": source_validation,
            "final_apply_approval_id": record.get("final_apply_approval_id"),
            "record_status": _source_record_status(record),
            "disabled_dry_run_final_approval_recorded": _source_decision_effect(record).get("disabled_dry_run_final_approval_recorded") is True,
            "mutation_plan_write_enabled": record.get("mutation_plan_write_enabled") is True,
            "mutation_plan_apply_enabled": record.get("mutation_plan_apply_enabled") is True,
        },
        "current_settings": {
            "project_version": _get_cfg_path(cfg, "project.version", None),
            "score_weights_path": "research.score_weights",
            "score_weights": current_weights,
        },
        "candidate": {
            "production_candidate_profile": profile_name,
            "candidate_weights_source": candidate_weights_source,
            "candidate_weights_present": bool(candidate_weights),
            "candidate_weight_reasons": candidate_weight_reasons,
            "score_weights": candidate_weights,
        },
        "score_weight_diff": diff,
        "settings_yaml_diff_artifact": artifact,
        "settings_write_preview_export": {
            "export_packet_created": True,
            "settings_write_preview_export_enabled": policy.get("settings_write_preview_export_enabled") is True,
            "candidate_settings_yaml_export_created": True,
            "unified_diff_export_created": True,
            "settings_write_enabled": False,
            "config_write_enabled": False,
            "runtime_score_weight_write_enabled": False,
            "settings_score_weight_write_enabled": False,
        },
        "policy": policy,
        "application_stub": {
            "status": "disabled_stub",
            "settings_write_enabled": False,
            "config_write_enabled": False,
            "reason": "Step267 exports a settings-write preview only. settings.yaml writes and score-weight mutation remain disabled.",
        },
        "safety_boundaries": {
            "preview_only": True,
            "settings_write_preview_export_only": True,
            "auto_apply_selected_profile": False,
            "selected_profile_written_to_settings": False,
            "settings_file_write_enabled": False,
            "settings_file_written": False,
            "runtime_score_weights_mutated": False,
            "settings_score_weights_mutated": False,
            "production_profile_auto_applied": False,
            "config_mutated": False,
            "live_trading_allowed": False,
            "order_routing_enabled": False,
            "testnet_order_submission_allowed": False,
            "real_telegram_send_allowed": False,
            "external_order_submission_performed": False,
            "canonical_live_execution_port_performed": False,
            "canonical_testnet_execution_port_performed": False,
            "root_package_deletion_performed": False,
            "root_package_deletion_deferred": True,
            "missing_canonical_module_count": 2,
        },
    }
    return packet


def validate_step267_disabled_settings_write_preview_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    preview = packet.get("preview") if isinstance(packet.get("preview"), Mapping) else {}
    source = packet.get("source") if isinstance(packet.get("source"), Mapping) else {}
    candidate = packet.get("candidate") if isinstance(packet.get("candidate"), Mapping) else {}
    artifact = packet.get("settings_yaml_diff_artifact") if isinstance(packet.get("settings_yaml_diff_artifact"), Mapping) else {}
    export = packet.get("settings_write_preview_export") if isinstance(packet.get("settings_write_preview_export"), Mapping) else {}
    policy = packet.get("policy") if isinstance(packet.get("policy"), Mapping) else {}
    stub = packet.get("application_stub") if isinstance(packet.get("application_stub"), Mapping) else {}
    safety = packet.get("safety_boundaries") if isinstance(packet.get("safety_boundaries"), Mapping) else {}
    status = preview.get("preview_status")
    allowed_statuses = {_READY_PREVIEW_STATUS, _BLOCKED_PREVIEW_STATUS, _INVALID_PREVIEW_STATUS}

    checks = {
        "version_matches_step267": packet.get("version") == STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION,
        "settings_write_preview_id_present": bool(packet.get("settings_write_preview_id")),
        "source_step266_version_matches": packet.get("source_final_apply_approval_version") == STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
        "preview_status_allowed": status in allowed_statuses,
        "ready_requires_source_approved": status != _READY_PREVIEW_STATUS or packet.get("source_record_status") == _APPROVED_SOURCE_STATUS,
        "ready_requires_candidate_weights": status != _READY_PREVIEW_STATUS or candidate.get("candidate_weights_present") is True,
        "source_mutation_plan_disabled": source.get("mutation_plan_write_enabled") is False and source.get("mutation_plan_apply_enabled") is False,
        "artifact_has_target_yaml_path": artifact.get("target_yaml_path") == "research.score_weights",
        "artifact_has_candidate_settings_yaml": status != _READY_PREVIEW_STATUS or (isinstance(artifact.get("candidate_settings_yaml"), str) and bool(artifact.get("candidate_settings_yaml"))),
        "artifact_has_unified_diff": isinstance(artifact.get("unified_diff"), str),
        "artifact_hashes_present": status != _READY_PREVIEW_STATUS or (bool(artifact.get("current_settings_yaml_sha256")) and bool(artifact.get("candidate_settings_yaml_sha256"))),
        "ready_requires_settings_file_exists": status != _READY_PREVIEW_STATUS or artifact.get("settings_file_exists") is True,
        "preview_timestamp_canonical": is_canonical_utc_timestamp(preview.get("timestamp_utc")),
        "export_packet_created": export.get("export_packet_created") is True,
        "export_settings_write_disabled": export.get("settings_write_enabled") is False and export.get("config_write_enabled") is False,
        "policy_blocks_runtime_write": policy.get("runtime_score_weight_write_enabled") is False,
        "policy_blocks_settings_write": policy.get("settings_score_weight_write_enabled") is False,
        "policy_blocks_config_write": policy.get("config_write_enabled") is False and policy.get("settings_file_write_enabled") is False,
        "application_stub_disabled": stub.get("status") == "disabled_stub" and stub.get("settings_write_enabled") is False,
        "safety_blocks_runtime_mutation": safety.get("runtime_score_weights_mutated") is False,
        "safety_blocks_settings_mutation": safety.get("settings_score_weights_mutated") is False,
        "safety_blocks_file_write": safety.get("settings_file_written") is False,
        "safety_blocks_live_order_telegram": safety.get("live_trading_allowed") is False and safety.get("order_routing_enabled") is False and safety.get("external_order_submission_performed") is False and safety.get("real_telegram_send_allowed") is False,
        "missing_canonical_module_count_locked": safety.get("missing_canonical_module_count") == 2,
    }
    return {
        "schema_version": STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION,
        "valid": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
    }


def apply_step267_disabled_settings_write_preview_stub(packet: Mapping[str, Any], cfg: Any = None) -> dict[str, Any]:
    """Disabled settings-write surface.

    Returns the rendered preview metadata while guaranteeing that settings.yaml and
    runtime score weights are not mutated.
    """
    before = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else {}
    validation = validate_step267_disabled_settings_write_preview_packet(packet)
    after = deepcopy(_get_cfg_path(cfg, "research.score_weights", {})) if cfg is not None else before
    artifact = packet.get("settings_yaml_diff_artifact") if isinstance(packet.get("settings_yaml_diff_artifact"), Mapping) else {}
    preview = packet.get("preview") if isinstance(packet.get("preview"), Mapping) else {}
    return {
        "status": "DISABLED_STUB",
        "reason": "Step267 settings-write preview/export does not write config/settings.yaml or mutate runtime score weights.",
        "settings_write_preview_id": packet.get("settings_write_preview_id"),
        "preview_status": preview.get("preview_status"),
        "validation_valid": validation.get("valid") is True,
        "score_weights_before": before,
        "score_weights_after": after,
        "runtime_score_weights_mutated": False,
        "settings_score_weights_mutated": False,
        "settings_file_written": False,
        "config_mutated": False,
        "candidate_settings_yaml_sha256": artifact.get("candidate_settings_yaml_sha256"),
        "settings_write_enabled": False,
        "config_write_enabled": False,
        "live_trading_allowed": False,
        "order_routing_enabled": False,
        "external_order_submission_performed": False,
        "real_telegram_send_allowed": False,
    }
