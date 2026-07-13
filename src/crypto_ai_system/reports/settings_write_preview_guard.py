from __future__ import annotations

import difflib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

SETTINGS_WRITE_PREVIEW_GUARD_VERSION = "step302_settings_write_preview_guard_v2"
SETTINGS_WRITE_PREVIEW_GUARD_REGISTRY_NAME = "settings_write_preview_guard_registry"

STATUS_CREATED_REVIEW_ONLY = "SETTINGS_WRITE_PREVIEW_CREATED_REVIEW_ONLY"
STATUS_CREATED_BLOCKED_REVIEW_ONLY = "SETTINGS_WRITE_PREVIEW_CREATED_BLOCKED_REVIEW_ONLY"
STATUS_BLOCKED_SETTINGS_SOURCE_MISSING = "SETTINGS_WRITE_PREVIEW_BLOCKED_SETTINGS_SOURCE_MISSING"
STATUS_BLOCKED_SETTINGS_SOURCE_INVALID = "SETTINGS_WRITE_PREVIEW_BLOCKED_SETTINGS_SOURCE_INVALID"

TARGET_SETTINGS_FILE = "config/settings.yaml"
TARGET_YAML_PATH = "research.score_weights"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
SETTINGS_FILE_WRITE_ENABLED_BY_THIS_MODULE = False
APPLY_PREVIEW_ENABLED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _preview_root(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.settings_write_preview_dir", "storage/settings_write_previews")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    value = read_json(_latest_dir(cfg) / name, default={})
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_side_effect(payload: Mapping[str, Any]) -> bool:
    return any(
        _bool(payload.get(name))
        for name in [
            "live_trading_allowed_by_this_module",
            "runtime_settings_mutated",
            "score_weights_mutated",
            "auto_promotion_allowed",
            "candidate_profile_applied",
            "approval_packet_created",
            "approval_packet_created_by_this_module",
            "settings_write_preview_applied",
            "live_order_executed",
            "external_order_submission_performed",
            "adapter_called",
        ]
    )


def _candidate_status_ready(candidate: Mapping[str, Any]) -> bool:
    return candidate.get("candidate_profile_created") is True and _text(candidate.get("status")) in {
        "review_only",
        "paper_candidate",
        "approval_packet_ready",
        "draft",
    }


def _approval_status_ready(approval: Mapping[str, Any]) -> bool:
    status = _text(approval.get("validation_status") or approval.get("approval_validation_status"))
    return status in {"valid", "approved", "approved_review_only", "approval_validated"}


def _coerce_weights(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, float] = {}
    for key, raw in value.items():
        try:
            out[str(key)] = float(raw)
        except (TypeError, ValueError):
            return {}
    return out


def _candidate_score_weights(candidate: Mapping[str, Any]) -> tuple[dict[str, float], str | None]:
    for key in ["proposed_score_weights", "candidate_score_weights", "score_weights", "research_score_weights"]:
        weights = _coerce_weights(candidate.get(key))
        if weights:
            return weights, key
    snapshot = candidate.get("performance_snapshot")
    if isinstance(snapshot, Mapping):
        for key in ["proposed_score_weights", "candidate_score_weights", "score_weights"]:
            weights = _coerce_weights(snapshot.get(key))
            if weights:
                return weights, f"performance_snapshot.{key}"
    return {}, None


def _read_current_settings(cfg: AppConfig, settings_path: Path | None = None) -> tuple[str, dict[str, Any], str, bool, str | None]:
    path = settings_path or (cfg.root / TARGET_SETTINGS_FILE)
    if not path.exists():
        return "", {}, str(path), False, "SETTINGS_SOURCE_FILE_MISSING"
    try:
        text = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(text) or {}
    except Exception as exc:
        return "", {}, str(path), True, f"SETTINGS_SOURCE_FILE_INVALID:{type(exc).__name__}"
    if not isinstance(parsed, dict):
        return text, {}, str(path), True, "SETTINGS_SOURCE_FILE_NOT_MAPPING"
    return text, parsed, str(path), True, None


def _set_nested(data: Mapping[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = deepcopy(dict(data))
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


def _make_diff(current_yaml: str, candidate_yaml: str, *, blocked_reasons: list[str], candidate_id: str | None, approval_status: str | None) -> str:
    diff = "".join(
        difflib.unified_diff(
            current_yaml.splitlines(keepends=True),
            candidate_yaml.splitlines(keepends=True),
            fromfile=TARGET_SETTINGS_FILE,
            tofile=f"{TARGET_SETTINGS_FILE}.disabled-preview",
        )
    )
    header = "\n".join(
        [
            "# disabled_settings_write_preview.diff",
            "# Step302 Settings Write Preview Guard v2",
            "# REVIEW ONLY. This diff must never be applied automatically.",
            f"# candidate_profile_id: {candidate_id or '<no-candidate-profile>'}",
            f"# approval_validation_status: {approval_status or 'missing'}",
            f"# blocked_reasons: {', '.join(blocked_reasons) if blocked_reasons else 'NONE'}",
            "# Runtime settings mutation: disabled",
            "# Runtime score_weights mutation: disabled",
            "# Settings file write: disabled",
            "# Apply preview: disabled",
            "# Signed testnet promotion: disabled",
            "# Live promotion: disabled",
            "# Automatic apply: disabled",
            "",
        ]
    )
    return header + (diff if diff else "# No YAML value changes generated by this preview guard.\n")


def build_settings_write_preview_guard(
    *,
    cfg: AppConfig | None = None,
    candidate_profile: Mapping[str, Any] | None = None,
    approval_registry: Mapping[str, Any] | None = None,
    settings_path: Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    candidate = dict(candidate_profile or _read_latest_json(cfg, "candidate_profile.json"))
    approval = dict(approval_registry or _read_latest_json(cfg, "approval_registry_record.json"))
    current_yaml, current_settings, resolved_settings_path, exists, settings_error = _read_current_settings(cfg, settings_path)

    blocked_reasons: list[str] = []
    if not exists:
        blocked_reasons.append("SETTINGS_SOURCE_FILE_MISSING")
    elif settings_error:
        blocked_reasons.append(settings_error)
    if not candidate:
        blocked_reasons.append("CANDIDATE_PROFILE_MISSING")
    elif not _candidate_status_ready(candidate):
        blocked_reasons.append("CANDIDATE_PROFILE_NOT_READY_FOR_SETTINGS_PREVIEW")
    if candidate and _unsafe_side_effect(candidate):
        blocked_reasons.append("CANDIDATE_PROFILE_UNSAFE_SIDE_EFFECT_FLAG_DETECTED")
    if not approval:
        blocked_reasons.append("APPROVAL_REGISTRY_MISSING")
    elif not _approval_status_ready(approval):
        blocked_reasons.append("APPROVAL_REGISTRY_NOT_VALID_FOR_SETTINGS_PREVIEW")
    if approval and _unsafe_side_effect(approval):
        blocked_reasons.append("APPROVAL_REGISTRY_UNSAFE_SIDE_EFFECT_FLAG_DETECTED")

    proposed_weights, proposed_source = _candidate_score_weights(candidate)
    candidate_settings = deepcopy(current_settings)
    candidate_settings_changed = False
    if exists and current_settings and proposed_weights and not any(reason.startswith("SETTINGS_SOURCE") for reason in blocked_reasons):
        candidate_settings = _set_nested(current_settings, TARGET_YAML_PATH, proposed_weights)
        candidate_settings_changed = candidate_settings != current_settings
    elif exists and current_settings and not proposed_weights:
        blocked_reasons.append("CANDIDATE_SCORE_WEIGHTS_MISSING_FOR_TARGET_PATH")

    if not exists:
        status = STATUS_BLOCKED_SETTINGS_SOURCE_MISSING
        candidate_yaml = "# SETTINGS SOURCE FILE MISSING. No candidate settings rendered.\n"
        current_hash = None
    elif settings_error:
        status = STATUS_BLOCKED_SETTINGS_SOURCE_INVALID
        candidate_yaml = "# SETTINGS SOURCE FILE INVALID. No candidate settings rendered.\n"
        current_hash = sha256_json({"raw_settings_yaml": current_yaml}) if current_yaml else None
    else:
        status = STATUS_CREATED_REVIEW_ONLY if not blocked_reasons else STATUS_CREATED_BLOCKED_REVIEW_ONLY
        candidate_yaml = _dump_yaml(candidate_settings)
        current_hash = sha256_json({"raw_settings_yaml": current_yaml})

    blocked_reasons = sorted(dict.fromkeys(reason for reason in blocked_reasons if reason))
    approval_status = _text(approval.get("validation_status") or approval.get("approval_validation_status")) or None
    diff_text = _make_diff(
        current_yaml if exists else "",
        candidate_yaml,
        blocked_reasons=blocked_reasons,
        candidate_id=_text(candidate.get("candidate_profile_id")) or None,
        approval_status=approval_status,
    )

    identity = {
        "version": SETTINGS_WRITE_PREVIEW_GUARD_VERSION,
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "approval_registry_record_id": approval.get("approval_registry_record_id"),
        "target_yaml_path": TARGET_YAML_PATH,
        "current_settings_sha256": current_hash,
        "candidate_settings_sha256": sha256_json({"candidate_settings_yaml": candidate_yaml}),
        "created_at_utc": utc_now_canonical(),
    }
    preview_id = stable_id("settings_write_preview", identity, 24)
    return {
        "settings_write_preview_guard_id": preview_id,
        "settings_write_preview_guard_version": SETTINGS_WRITE_PREVIEW_GUARD_VERSION,
        "status": status,
        "blocked_reasons": blocked_reasons,
        "target_settings_file": TARGET_SETTINGS_FILE,
        "resolved_settings_file": resolved_settings_path,
        "target_yaml_path": TARGET_YAML_PATH,
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "candidate_profile_status": candidate.get("status"),
        "candidate_profile_creation_status": candidate.get("creation_status"),
        "approval_registry_record_id": approval.get("approval_registry_record_id"),
        "approval_registry_record_sha256": approval.get("approval_registry_record_sha256"),
        "approval_validation_status": approval_status,
        "proposed_score_weights_source": proposed_source,
        "candidate_settings_changed": candidate_settings_changed,
        "current_settings_sha256": current_hash,
        "candidate_settings_sha256": sha256_json({"candidate_settings_yaml": candidate_yaml}),
        "disabled_settings_write_preview_diff_sha256": sha256_json({"disabled_settings_write_preview_diff": diff_text}),
        "candidate_settings_yaml": candidate_yaml,
        "disabled_settings_write_preview_diff": diff_text,
        "review_only": True,
        "manual_settings_write_review_required": True,
        "settings_file_write_enabled": SETTINGS_FILE_WRITE_ENABLED_BY_THIS_MODULE,
        "apply_preview_enabled": APPLY_PREVIEW_ENABLED_BY_THIS_MODULE,
        "settings_write_preview_applied": False,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
        "candidate_profile_applied": CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE,
        "auto_promotion_allowed": AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "signed_testnet_promotion_allowed": SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "testnet_order_submission_allowed_by_this_module": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "created_at_utc": identity["created_at_utc"],
    }


def build_and_persist_settings_write_preview_guard(
    *,
    cfg: AppConfig | None = None,
    candidate_profile: Mapping[str, Any] | None = None,
    approval_registry: Mapping[str, Any] | None = None,
    settings_path: Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    preview = build_settings_write_preview_guard(
        cfg=cfg,
        candidate_profile=candidate_profile,
        approval_registry=approval_registry,
        settings_path=settings_path,
    )
    preview_dir = _preview_root(cfg) / preview["settings_write_preview_guard_id"]
    preview_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = preview_dir / "candidate_settings.yaml"
    diff_path = preview_dir / "disabled_settings_write_preview.diff"
    manifest_path = preview_dir / "settings_write_preview_guard_manifest.json"

    candidate_path.write_text(str(preview.pop("candidate_settings_yaml")), encoding="utf-8")
    diff_path.write_text(str(preview.pop("disabled_settings_write_preview_diff")), encoding="utf-8")

    manifest = {
        **preview,
        "preview_dir": str(preview_dir),
        "candidate_settings_path": str(candidate_path),
        "disabled_settings_write_preview_diff_path": str(diff_path),
        "candidate_settings_file_sha256": sha256_file(candidate_path),
        "disabled_settings_write_preview_diff_file_sha256": sha256_file(diff_path),
    }
    manifest["settings_write_preview_guard_manifest_sha256"] = sha256_json({k: v for k, v in manifest.items() if k != "settings_write_preview_guard_manifest_sha256"})
    atomic_write_json(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)

    registry_record = append_registry_record(
        registry_path(cfg, SETTINGS_WRITE_PREVIEW_GUARD_REGISTRY_NAME),
        manifest,
        registry_name=SETTINGS_WRITE_PREVIEW_GUARD_REGISTRY_NAME,
        id_field="settings_write_preview_guard_registry_record_id",
        hash_field="settings_write_preview_guard_registry_record_sha256",
        id_prefix="settings_write_preview_registry",
    )
    manifest["settings_write_preview_guard_registry_record_id"] = registry_record["settings_write_preview_guard_registry_record_id"]
    manifest["settings_write_preview_guard_registry_record_sha256"] = registry_record["settings_write_preview_guard_registry_record_sha256"]
    atomic_write_json(manifest_path, manifest)
    atomic_write_json(latest / "settings_write_preview_guard_manifest.json", manifest)
    atomic_write_json(latest / "settings_write_preview_guard_registry_record.json", registry_record)
    return manifest


def run_settings_write_preview_guard_latest(cfg: AppConfig | None = None) -> dict[str, Any]:
    return build_and_persist_settings_write_preview_guard(cfg=cfg or load_config())
