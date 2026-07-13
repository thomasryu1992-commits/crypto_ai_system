from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_17_final_pre_executor_review_packet import (
    persist_phase7_17_final_pre_executor_review_packet_report,
)

PHASE8_1_VERSION = "phase8_1_secret_manager_key_handling_design_v1"
PHASE8_1_REGISTRY_NAME = "phase8_1_secret_manager_key_handling_design_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE8_1_SECRET_MANAGER_KEY_HANDLING_DESIGN_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE8_1_SECRET_MANAGER_KEY_HANDLING_DESIGN_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE7_17_FILES = {
    "phase7_17_report": "phase7_17_final_pre_executor_review_packet_report.json",
    "phase7_final_packet": "phase7_final_pre_executor_review_packet_review_only.json",
    "phase7_final_guard": "phase7_final_pre_executor_review_guard_report.json",
}

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
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
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
]

DESIGN_REQUIRED_FIELDS = [
    "design_type",
    "phase8_1_version",
    "source_phase8_1_report_id",
    "review_only",
    "design_only",
    "metadata_only_key_handling",
    "not_runtime_authority",
    "secret_values_never_logged",
    "secret_values_never_persisted",
    "secret_files_not_read_or_created",
    "only_key_references_and_fingerprints_in_reports",
    "allowed_key_metadata_fields",
    "forbidden_secret_material_fields",
    "required_secret_provider_capabilities",
    "required_testnet_key_scope",
    "required_fail_closed_conditions",
    "phase8_2_write_path_dry_validation_required",
    "phase8_3_hot_path_risk_gate_required",
    "phase8_4_final_guard_required",
    "phase9_explicit_single_order_intake_required",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
]

ALLOWED_KEY_METADATA_FIELDS = [
    "secret_provider_name",
    "secret_provider_reference_id",
    "metadata_only_key_reference_id",
    "metadata_only_key_fingerprint_sha256",
    "venue",
    "environment",
    "key_scope_label",
    "created_at_utc",
    "last_validated_at_utc",
]

FORBIDDEN_SECRET_MATERIAL_FIELDS = [
    "api_key",
    "api_key_value",
    "api_secret",
    "api_secret_value",
    "private_key",
    "private_key_value",
    "passphrase",
    "passphrase_value",
    "mnemonic",
    "seed_phrase",
    "raw_secret",
    "secret_value",
    "secret_file_path",
    "secret_file_contents",
    "withdrawal_key",
    "transfer_key",
]

REQUIRED_TESTNET_KEY_SCOPE = {
    "environment": "signed_testnet_only",
    "mainnet_or_live_key_allowed": False,
    "withdrawal_permission_allowed": False,
    "transfer_permission_allowed": False,
    "admin_permission_allowed": False,
    "leverage_or_margin_mutation_allowed": False,
    "read_account_allowed_for_future_validation": True,
    "write_trade_permission_currently_enabled": False,
    "write_trade_permission_may_only_be_considered_after_phase8_final_guard_and_phase9_intake": True,
}

_SECRET_VALUE_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
]


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(fields)


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase8_1_report_sha256",
        "secret_key_handling_design_sha256",
        "secret_key_handling_design_guard_report_sha256",
        "phase7_17_report_sha256",
        "final_pre_executor_review_packet_sha256",
        "final_pre_executor_review_guard_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("design_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _phase7_17_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data:
        return False
    if data.get("blocked") is True or data.get("fail_closed") is True:
        return False
    unsafe = _unsafe_fields(data)
    if unsafe:
        return False
    if name == "phase7_17_report":
        return data.get("phase7_final_pre_executor_review_ready") is True and data.get("phase8_preparation_review_may_begin") is True
    if name == "phase7_final_packet":
        return data.get("packet_type") == "phase7_17_final_pre_executor_review_packet_review_only" and data.get("phase8_preparation_review_may_begin") is True
    if name == "phase7_final_guard":
        return data.get("guard_passed") is True and data.get("phase8_preparation_review_may_begin") is True
    return True


def _find_secret_material(value: Any, *, path: str = "root") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            item_path = f"{path}.{key_text}"
            if key_text in FORBIDDEN_SECRET_MATERIAL_FIELDS and item not in (None, "", "NEVER_STORE_SECRET_VALUE", "FORBIDDEN"):
                findings.append(f"FORBIDDEN_SECRET_FIELD_PRESENT:{item_path}")
            findings.extend(_find_secret_material(item, path=item_path))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            findings.extend(_find_secret_material(item, path=f"{path}[{idx}]"))
    elif isinstance(value, str):
        lower_path = path.lower()
        if value in {"METADATA_ONLY_PLACEHOLDER", "NEVER_STORE_SECRET_VALUE", "FORBIDDEN"}:
            return findings
        if lower_path.endswith("sha256") or "fingerprint" in lower_path or "hash_summary" in lower_path:
            return findings
        for pattern in _SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                findings.append(f"POSSIBLE_SECRET_VALUE_PATTERN:{path}")
                break
    return findings


def validate_secret_key_handling_design(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in DESIGN_REQUIRED_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    secret_findings = _find_secret_material(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_SECRET_KEY_HANDLING_DESIGN_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_SECRET_KEY_HANDLING_DESIGN_FLAGS:" + ",".join(unsafe))
    if secret_findings:
        blockers.append("SECRET_MATERIAL_DETECTED_IN_DESIGN:" + ",".join(sorted(dict.fromkeys(secret_findings))))
    if data.get("design_type") != "phase8_1_secret_manager_key_handling_design_review_only":
        blockers.append("INVALID_SECRET_KEY_HANDLING_DESIGN_TYPE")
    for field in (
        "review_only",
        "design_only",
        "metadata_only_key_handling",
        "not_runtime_authority",
        "secret_values_never_logged",
        "secret_values_never_persisted",
        "secret_files_not_read_or_created",
        "only_key_references_and_fingerprints_in_reports",
        "phase8_2_write_path_dry_validation_required",
        "phase8_3_hot_path_risk_gate_required",
        "phase8_4_final_guard_required",
        "phase9_explicit_single_order_intake_required",
        "blocks_signed_testnet_execution",
        "blocks_order_submission",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_SECRET_KEY_HANDLING_CONFIRMATION_NOT_TRUE:{field}")
    for field in (
        "secret_value_accessed",
        "secret_file_read",
        "secret_file_created",
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
        "actual_executor_enablement_performed",
        "actual_order_submission_performed",
        "ready_for_signed_testnet_execution",
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
    ):
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_SECRET_KEY_HANDLING_FALSE_FLAG_NOT_FALSE:{field}")
    if data.get("allowed_key_metadata_fields") != ALLOWED_KEY_METADATA_FIELDS:
        blockers.append("ALLOWED_KEY_METADATA_FIELDS_INVALID")
    if data.get("forbidden_secret_material_fields") != FORBIDDEN_SECRET_MATERIAL_FIELDS:
        blockers.append("FORBIDDEN_SECRET_MATERIAL_FIELDS_INVALID")
    if data.get("required_testnet_key_scope") != REQUIRED_TESTNET_KEY_SCOPE:
        blockers.append("REQUIRED_TESTNET_KEY_SCOPE_INVALID")
    valid = not blockers
    return {
        "secret_key_handling_design_valid_review_only": valid,
        "secret_key_handling_design_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "secret_material_findings": sorted(dict.fromkeys(secret_findings)),
        "secret_key_handling_design_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_secret_key_design(*, report_id: str, phase7_sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    source_summary = {name: _source_summary(name, payload) for name, payload in phase7_sources.items()}
    design: dict[str, Any] = {
        "design_type": "phase8_1_secret_manager_key_handling_design_review_only",
        "phase8_1_version": PHASE8_1_VERSION,
        "source_phase8_1_report_id": report_id,
        "source_phase7_17_evidence_hash_summary": source_summary,
        "review_only": True,
        "design_only": True,
        "metadata_only_key_handling": True,
        "not_runtime_authority": True,
        "secret_values_never_logged": True,
        "secret_values_never_persisted": True,
        "secret_files_not_read_or_created": True,
        "only_key_references_and_fingerprints_in_reports": True,
        "allowed_key_metadata_fields": ALLOWED_KEY_METADATA_FIELDS,
        "forbidden_secret_material_fields": FORBIDDEN_SECRET_MATERIAL_FIELDS,
        "required_secret_provider_capabilities": {
            "runtime_injection_only": True,
            "redacted_logging_required": True,
            "metadata_only_fingerprint_export_allowed": True,
            "raw_key_material_export_allowed": False,
            "secret_file_mount_required": False,
            "secret_file_read_allowed": False,
            "secret_file_creation_allowed": False,
        },
        "required_testnet_key_scope": REQUIRED_TESTNET_KEY_SCOPE,
        "required_fail_closed_conditions": [
            "missing_key_reference_id",
            "missing_key_fingerprint_sha256",
            "fingerprint_format_invalid",
            "mainnet_or_live_key_detected",
            "withdrawal_transfer_or_admin_scope_detected",
            "secret_value_present_in_payload_or_artifact",
            "secret_file_path_or_contents_present",
            "raw_secret_logging_attempt_detected",
            "runtime_executor_flag_truthy",
            "phase7_17_final_pre_executor_review_not_ready",
        ],
        "phase8_2_write_path_dry_validation_required": True,
        "phase8_3_hot_path_risk_gate_required": True,
        "phase8_4_final_guard_required": True,
        "phase9_explicit_single_order_intake_required": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "phase8_1_does_not_validate_actual_secret_values": True,
        "phase8_1_does_not_create_or_read_secret_files": True,
        "phase8_1_does_not_enable_exchange_write_permissions": True,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
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
        "created_at_utc": created_at_utc,
    }
    design["secret_key_handling_design_sha256"] = sha256_json(design)
    return design


def _build_guard(*, report_id: str, design: Mapping[str, Any], validation: Mapping[str, Any], phase7_ready: bool, created_at_utc: str) -> dict[str, Any]:
    guard_passed = phase7_ready and validation.get("secret_key_handling_design_valid_review_only") is True
    guard = {
        "guard_type": "phase8_1_secret_key_handling_design_guard_review_only",
        "phase8_1_version": PHASE8_1_VERSION,
        "source_phase8_1_report_id": report_id,
        "review_only": True,
        "secret_key_handling_design_guard_only": True,
        "guard_passed": guard_passed,
        "phase7_17_final_review_ready": phase7_ready,
        "design_validation": dict(validation),
        "phase8_2_write_path_dry_validation_may_begin": guard_passed,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }
    guard["secret_key_handling_design_guard_report_sha256"] = sha256_json(guard)
    return guard


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 8.1 Secret Manager / Key Handling Design - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase defines metadata-only key handling for future signed testnet preparation. It does not read key values, create secret files, enable executors, or call order endpoints.",
            "",
            "## Result",
            "",
            f"- Secret/key handling design ready: `{report.get('phase8_1_secret_key_design_ready')}`",
            f"- Guard passed: `{report.get('secret_key_handling_design_guard_passed')}`",
            f"- Phase 8.2 write-path dry validation may begin: `{report.get('phase8_2_write_path_dry_validation_may_begin')}`",
            "",
            "## Safety Flags",
            "",
            "- `secret_value_accessed=false`",
            "- `secret_file_read=false`",
            "- `secret_file_created=false`",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase8_1_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase8_1_secret_manager_key_handling_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_17_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_17_first:
        persist_phase7_17_final_pre_executor_review_packet_report(cfg=cfg)

    phase7_sources = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_PHASE7_17_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in phase7_sources.items()}
    missing = [name for name, payload in phase7_sources.items() if not payload]
    phase7_not_ready = [name for name, payload in phase7_sources.items() if not _phase7_17_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in phase7_sources.items() if _unsafe_fields(payload)}

    preliminary_blockers: list[str] = []
    preliminary_blockers.extend([f"MISSING_PHASE8_1_REQUIRED_PHASE7_17_EVIDENCE:{name}" for name in missing])
    preliminary_blockers.extend([f"PHASE8_1_PHASE7_17_EVIDENCE_NOT_READY:{name}" for name in phase7_not_ready])
    if unsafe:
        preliminary_blockers.extend([f"UNSAFE_PHASE8_1_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    preliminary_blockers = sorted(dict.fromkeys(str(item) for item in preliminary_blockers if item))
    phase7_ready = not preliminary_blockers

    preliminary_id = stable_id("phase8_1_secret_manager_key_handling_design", {"source_summary": source_summary, "created_at_utc": created}, 24)
    design = _build_secret_key_design(report_id=preliminary_id, phase7_sources=phase7_sources, created_at_utc=created)
    validation = validate_secret_key_handling_design(design)
    guard = _build_guard(report_id=preliminary_id, design=design, validation=validation, phase7_ready=phase7_ready, created_at_utc=created)

    blockers = list(preliminary_blockers)
    if validation.get("secret_key_handling_design_valid_review_only") is not True:
        blockers.extend(validation.get("secret_key_handling_design_blockers") or ["SECRET_KEY_HANDLING_DESIGN_INVALID"])
    if guard.get("guard_passed") is not True:
        blockers.append("SECRET_KEY_HANDLING_DESIGN_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report_id = stable_id(
        "phase8_1_secret_manager_key_handling_design",
        {
            "source_summary": source_summary,
            "design_hash": sha256_json(design),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    design["source_phase8_1_report_id"] = report_id
    design["secret_key_handling_design_sha256"] = sha256_json(design)
    validation = validate_secret_key_handling_design(design)
    guard = _build_guard(report_id=report_id, design=design, validation=validation, phase7_ready=phase7_ready, created_at_utc=created)

    report: dict[str, Any] = {
        "phase8_1_secret_manager_key_handling_design_id": report_id,
        "phase8_1_version": PHASE8_1_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "design_only": True,
        "metadata_only_key_handling": True,
        "phase8_1_secret_key_design_ready": ready,
        "secret_key_handling_design_created": True,
        "secret_key_handling_design_guard_created": True,
        "secret_key_handling_design_guard_passed": guard.get("guard_passed") is True,
        "phase8_2_write_path_dry_validation_may_begin": ready,
        "phase8_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "required_phase7_17_evidence_hash_summary": source_summary,
        "missing_required_phase7_17_evidence": missing,
        "phase7_17_evidence_not_ready": phase7_not_ready,
        "unsafe_flags_by_artifact": unsafe,
        "design_validation": validation,
        "block_reasons": blockers,
        "phase8_1_allowed_next_scope": "phase8_2_exchange_adapter_write_path_dry_validation_no_order_endpoint_calls" if ready else "resolve_phase8_1_secret_key_handling_design_blockers",
        "recommended_next_action": "start_phase8_2_write_path_dry_validation_keep_no_order_endpoint_calls" if ready else "inspect_phase8_1_blockers_and_rerun_phase7_17_then_phase8_1",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
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
    report["secret_key_handling_design_sha256"] = design["secret_key_handling_design_sha256"]
    report["secret_key_handling_design_guard_report_sha256"] = guard["secret_key_handling_design_guard_report_sha256"]
    report["phase8_1_report_sha256"] = sha256_json(report)
    return report, design, guard


def persist_phase8_1_secret_manager_key_handling_design_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_17_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase8_1_secret_manager_key_handling_design")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, design, guard = build_phase8_1_secret_manager_key_handling_design_report(cfg=cfg, run_phase7_17_first=run_phase7_17_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase8_1_secret_manager_key_handling_design_report.json", report)
    atomic_write_json(latest / "secret_manager_key_handling_design_review_only.json", design)
    atomic_write_json(latest / "secret_key_handling_design_guard_report.json", guard)
    (latest / "PHASE8_1_SECRET_MANAGER_KEY_HANDLING_DESIGN_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "secret_manager_key_handling_design_review_only.json", design)

    atomic_write_json(phase_dir / "phase8_1_secret_manager_key_handling_design_report.json", report)
    atomic_write_json(phase_dir / "secret_manager_key_handling_design_review_only.json", design)
    atomic_write_json(phase_dir / "secret_key_handling_design_guard_report.json", guard)
    (phase_dir / "PHASE8_1_SECRET_MANAGER_KEY_HANDLING_DESIGN_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE8_1_REGISTRY_NAME),
        {
            "phase8_1_secret_manager_key_handling_design_id": report.get("phase8_1_secret_manager_key_handling_design_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase8_1_secret_key_design_ready": report.get("phase8_1_secret_key_design_ready"),
            "phase8_2_write_path_dry_validation_may_begin": report.get("phase8_2_write_path_dry_validation_may_begin"),
            "secret_value_accessed": False,
            "secret_file_read": False,
            "secret_file_created": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
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
        registry_name=PHASE8_1_REGISTRY_NAME,
        id_field="phase8_1_secret_manager_key_handling_design_registry_record_id",
        hash_field="phase8_1_secret_manager_key_handling_design_registry_record_sha256",
        id_prefix="phase8_1_secret_manager_key_handling_design_registry_record",
    )
    atomic_write_json(latest / "phase8_1_secret_manager_key_handling_design_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase8_1_secret_manager_key_handling_design_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE8_1_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "validate_secret_key_handling_design",
    "build_phase8_1_secret_manager_key_handling_design_report",
    "persist_phase8_1_secret_manager_key_handling_design_report",
]
