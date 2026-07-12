from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_manual_final_confirmation import persist_phase9_2_manual_final_confirmation_report
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool, _unsafe_fields

PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_VERSION = "phase9_2_runtime_submit_action_boundary_v1"
PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_REGISTRY_NAME = "phase9_2_runtime_submit_action_boundary_registry"
STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED = "PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED_REVIEW_ONLY"
STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_BLOCKED = "PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_BLOCKED_REVIEW_ONLY"

SOURCE_FILES = {
    "phase9_2_manual_final_confirmation_report": "phase9_2_manual_final_confirmation_report.json",
    "phase9_2_manual_final_confirmation_readiness": "phase9_2_manual_final_confirmation_readiness_report.json",
    "phase9_2_final_approval_package": "phase9_2_final_approval_package_report.json",
    "phase9_2_final_submit_readiness": "phase9_2_final_submit_readiness_report.json",
}

RUNTIME_ACTION_BLOCKERS = [
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_EXPLICIT_RUNTIME_SUBMIT_APPROVAL_TEXT_NOT_PRESENT",
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_FRESH_ENDPOINT_TIME_RISK_REFRESH_AT_ACTION_TIME",
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_RUNTIME_SECRET_BINDING_AT_ACTION_TIME",
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_EXECUTOR_POLICY_APPLICATION_AT_ACTION_TIME",
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_ENDPOINT_POLICY_APPLICATION_AT_ACTION_TIME",
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_DUPLICATE_SUBMIT_LOCK_AT_ACTION_TIME",
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_SEPARATE_OPERATOR_FINAL_CONFIRMATION_COMMAND",
]

REQUIRED_TEMPLATE_FIELDS = [
    "phase9_2_runtime_submit_action_boundary_id",
    "action_scope",
    "explicit_runtime_submit_approval_present",
    "runtime_action_is_review_only",
    "runtime_action_is_blocked_until_explicit_approval",
    "max_order_count",
    "single_order_scope",
    "testnet_only",
    "fresh_endpoint_time_risk_refresh_required_at_action_time",
    "runtime_secret_binding_required_at_action_time",
    "executor_policy_application_required_at_action_time",
    "endpoint_policy_application_required_at_action_time",
    "duplicate_submit_lock_required_at_action_time",
    "phase9_2_order_submission_authorized",
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


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _hash(payload: Mapping[str, Any]) -> str:
    data = dict(payload or {})
    for key in [
        "phase9_2_manual_final_confirmation_report_sha256",
        "phase9_2_manual_final_confirmation_readiness_report_sha256",
        "phase9_2_final_approval_package_report_sha256",
        "phase9_2_final_submit_readiness_report_sha256",
        "phase9_2_runtime_submit_action_boundary_template_sha256",
        "phase9_2_runtime_submit_action_boundary_validation_report_sha256",
    ]:
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _disabled_payload() -> dict[str, Any]:
    payload = {field: False for field in FALSE_FLAGS}
    payload.update({
        "runtime_authority_granted": False,
        "runtime_authority_application_performed": False,
        "secret_manager_runtime_binding_performed": False,
        "executor_policy_application_performed": False,
        "endpoint_policy_application_performed": False,
        "endpoint_policy_changed": False,
        "testnet_order_submission_allowed": False,
        "signed_order_executor_enabled": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "runtime_submit_action_approved": False,
        "runtime_submit_action_executed": False,
        "runtime_submit_action_performed": False,
        "real_order_id_created": False,
        "real_order_submit_attempted": False,
        "order_endpoint_call_allowed": False,
        "order_status_endpoint_call_allowed": False,
        "cancel_endpoint_call_allowed": False,
        "http_request_allowed": False,
        "signature_creation_allowed": False,
        "signed_request_creation_allowed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    })
    return payload


def _unsafe_runtime_fields(payload: Mapping[str, Any]) -> list[str]:
    false_fields = set(_disabled_payload())
    return sorted(field for field in false_fields if _safe_bool(dict(payload or {}).get(field)))


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_2_manual_final_confirmation_report":
        return data.get("phase9_2_manual_final_confirmation_recorded") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_manual_final_confirmation_readiness":
        return data.get("manual_final_confirmation_ready") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_final_approval_package":
        return data.get("phase9_2_final_approval_package_recorded") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_final_submit_readiness":
        return data.get("phase9_2_ready_for_manual_final_confirmation") is True and data.get("phase9_2_order_submission_authorized") is False
    return True


def build_runtime_submit_action_boundary_template(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    manual = dict(sources.get("phase9_2_manual_final_confirmation_report") or {})
    final_pkg = dict(sources.get("phase9_2_final_approval_package") or {})
    action_id = stable_id("phase9_2_runtime_submit_action_boundary", {
        "manual": _hash(manual),
        "final_pkg": _hash(final_pkg),
    }, 24)
    payload = {
        "artifact_type": "phase9_2_runtime_submit_action_boundary_template_blocked_review_only",
        "phase9_2_runtime_submit_action_boundary_id": action_id,
        "phase9_2_runtime_submit_action_boundary_version": PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_VERSION,
        "review_only": True,
        "still_disabled": True,
        "blocked_runtime_action_boundary": True,
        "action_scope": "single_signed_testnet_order_runtime_submit_action_boundary_only",
        "source_phase9_2_manual_final_confirmation_hash": _hash(manual),
        "source_phase9_2_final_approval_package_hash": _hash(final_pkg),
        "explicit_runtime_submit_approval_present": False,
        "runtime_action_is_review_only": True,
        "runtime_action_is_blocked_until_explicit_approval": True,
        "runtime_action_does_not_submit_order": True,
        "max_order_count": 1,
        "single_order_scope": True,
        "testnet_only": True,
        "fresh_endpoint_time_risk_refresh_required_at_action_time": True,
        "runtime_secret_binding_required_at_action_time": True,
        "executor_policy_application_required_at_action_time": True,
        "endpoint_policy_application_required_at_action_time": True,
        "duplicate_submit_lock_required_at_action_time": True,
        "separate_operator_final_confirmation_command_required": True,
        **_disabled_payload(),
    }
    payload["phase9_2_runtime_submit_action_boundary_template_sha256"] = sha256_json(payload)
    return payload


def validate_runtime_submit_action_boundary_template(template: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(template or {})
    blockers: list[str] = []
    blockers.extend(f"PHASE9_2_RUNTIME_SUBMIT_ACTION_MISSING_FIELD:{field}" for field in REQUIRED_TEMPLATE_FIELDS if field not in data)
    if data.get("artifact_type") != "phase9_2_runtime_submit_action_boundary_template_blocked_review_only":
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_NOT_STILL_DISABLED_REVIEW_ONLY")
    if data.get("action_scope") != "single_signed_testnet_order_runtime_submit_action_boundary_only":
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_INVALID_SCOPE")
    for field in [
        "runtime_action_is_review_only",
        "runtime_action_is_blocked_until_explicit_approval",
        "runtime_action_does_not_submit_order",
        "single_order_scope",
        "testnet_only",
        "fresh_endpoint_time_risk_refresh_required_at_action_time",
        "runtime_secret_binding_required_at_action_time",
        "executor_policy_application_required_at_action_time",
        "endpoint_policy_application_required_at_action_time",
        "duplicate_submit_lock_required_at_action_time",
        "separate_operator_final_confirmation_command_required",
    ]:
        if data.get(field) is not True:
            blockers.append(f"PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRED_TRUE_FIELD_FALSE:{field}")
    if data.get("explicit_runtime_submit_approval_present") is not False:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_EXPLICIT_APPROVAL_PRESENT_UNEXPECTED")
    if data.get("max_order_count") != 1:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_MAX_ORDER_COUNT_NOT_ONE")
    for field in [
        "phase9_2_order_submission_authorized",
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "signed_order_executor_enabled",
        "place_order_enabled",
        "cancel_order_enabled",
        "runtime_submit_action_approved",
        "runtime_submit_action_executed",
        "real_order_id_created",
    ]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_RUNTIME_SUBMIT_ACTION_UNSAFE_FLAG:{field}")
    unsafe = _unsafe_runtime_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_UNSAFE_FIELDS:" + ",".join(unsafe))
    secret_like = [path for path in _find_secret_like_values(data) if "hash" not in path.lower() and "sha256" not in path.lower() and "fingerprint" not in path.lower() and "metadata" not in path.lower()]
    if secret_like:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like))
    valid = not blockers
    report = {
        "artifact_type": "phase9_2_runtime_submit_action_boundary_validation_report",
        "phase9_2_runtime_submit_action_boundary_template_valid": valid,
        "runtime_submit_action_boundary_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "runtime_submit_action_is_review_only": True,
        "runtime_submit_action_is_not_runtime_authority": True,
        "phase9_2_runtime_submit_action_boundary_ready_for_explicit_submit_approval_review_only": valid,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_disabled_payload(),
    }
    report["phase9_2_runtime_submit_action_boundary_validation_report_sha256"] = sha256_json(report)
    return report


def build_runtime_submit_action_readiness_report(template: Mapping[str, Any], validation: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    valid = dict(validation).get("runtime_submit_action_boundary_valid") is True
    report_id = stable_id("phase9_2_runtime_submit_action_readiness", {
        "template": _hash(template),
        "validation": _hash(validation),
        "manual": _hash(sources.get("phase9_2_manual_final_confirmation_report") or {}),
    }, 24)
    report = {
        "artifact_type": "phase9_2_runtime_submit_action_readiness_report_blocked_review_only",
        "phase9_2_runtime_submit_action_readiness_report_id": report_id,
        "version": PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_VERSION,
        "review_only": True,
        "still_disabled": True,
        "blocked_runtime_action_boundary": True,
        "source_runtime_submit_action_boundary_template_hash": _hash(template),
        "source_runtime_submit_action_boundary_validation_hash": _hash(validation),
        "source_manual_final_confirmation_hash": _hash(sources.get("phase9_2_manual_final_confirmation_report") or {}),
        "runtime_submit_action_boundary_valid": valid,
        "runtime_submit_action_ready_for_explicit_submit_approval_review_only": valid,
        "runtime_submit_action_approved": False,
        "runtime_submit_action_executed": False,
        "runtime_submit_action_performed": False,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "phase9_3_status_polling_may_begin": False,
        "remaining_runtime_submit_blockers": RUNTIME_ACTION_BLOCKERS,
        **_disabled_payload(),
    }
    report["phase9_2_runtime_submit_action_readiness_report_sha256"] = sha256_json(report)
    return report


def validate_runtime_submit_action_readiness_report(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    blockers: list[str] = []
    if data.get("artifact_type") != "phase9_2_runtime_submit_action_readiness_report_blocked_review_only":
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_READINESS_INVALID_ARTIFACT_TYPE")
    if data.get("runtime_submit_action_boundary_valid") is not True:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_READINESS_NOT_READY")
    for field in ["runtime_submit_action_approved", "runtime_submit_action_executed", "phase9_2_order_submission_authorized", "actual_order_submission_performed", "order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_RUNTIME_SUBMIT_ACTION_READINESS_UNSAFE_FLAG:{field}")
    unsafe = _unsafe_runtime_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_ACTION_READINESS_UNSAFE_FIELDS:" + ",".join(unsafe))
    valid = not blockers
    validation = {
        "artifact_type": "phase9_2_runtime_submit_action_readiness_validation_report",
        "phase9_2_runtime_submit_action_readiness_report_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "unsafe_truthy_fields": unsafe,
        **_disabled_payload(),
    }
    validation["phase9_2_runtime_submit_action_readiness_validation_report_sha256"] = sha256_json(validation)
    return validation


def _negative_fixture_results(template: Mapping[str, Any], readiness: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, tuple[str, Mapping[str, Any], Any]] = {
        "explicit_submit_approval_true": ("template", {"explicit_runtime_submit_approval_present": True}, validate_runtime_submit_action_boundary_template),
        "max_order_count_gt_one": ("template", {"max_order_count": 2}, validate_runtime_submit_action_boundary_template),
        "missing_fresh_risk_refresh_requirement": ("template", {"fresh_endpoint_time_risk_refresh_required_at_action_time": False}, validate_runtime_submit_action_boundary_template),
        "runtime_secret_binding_performed_true": ("readiness", {"secret_manager_runtime_binding_performed": True}, validate_runtime_submit_action_readiness_report),
        "executor_enabled_true": ("readiness", {"signed_order_executor_enabled": True}, validate_runtime_submit_action_readiness_report),
        "order_authorized_true": ("readiness", {"phase9_2_order_submission_authorized": True}, validate_runtime_submit_action_readiness_report),
        "order_endpoint_called_true": ("readiness", {"order_endpoint_called": True}, validate_runtime_submit_action_readiness_report),
        "signature_created_true": ("readiness", {"signature_created": True}, validate_runtime_submit_action_readiness_report),
        "http_request_sent_true": ("readiness", {"http_request_sent": True}, validate_runtime_submit_action_readiness_report),
        "raw_secret_value_present": ("template", {"api_secret": "raw-secret-value-should-block"}, validate_runtime_submit_action_boundary_template),
    }
    base = {"template": dict(template), "readiness": dict(readiness)}
    results: dict[str, dict[str, Any]] = {}
    for name, (kind, patch, validator) in cases.items():
        payload = dict(base[kind])
        payload.update(patch)
        validation = validator(payload)
        results[name] = {
            "fixture_name": name,
            "artifact_kind": kind,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    return {
        "artifact_type": "phase9_2_runtime_submit_action_boundary_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] and item["fail_closed"] for item in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
    }


def build_phase9_2_runtime_submit_action_boundary_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_manual_confirmation_first: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    if run_manual_confirmation_first:
        persist_phase9_2_manual_final_confirmation_report(cfg=cfg, run_final_approval_first=True)
    created = utc_now_canonical()
    sources = {name: _read_latest_json(cfg, filename) for name, filename in SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe_sources = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    template = build_runtime_submit_action_boundary_template(sources)
    validation = validate_runtime_submit_action_boundary_template(template)
    readiness = build_runtime_submit_action_readiness_report(template, validation, sources)
    readiness_validation = validate_runtime_submit_action_readiness_report(readiness)
    negative_results = _negative_fixture_results(template, readiness)
    recorded = (
        not missing
        and not not_ready
        and not unsafe_sources
        and validation["runtime_submit_action_boundary_valid"] is True
        and readiness_validation["phase9_2_runtime_submit_action_readiness_report_valid"] is True
        and negative_results["all_negative_fixtures_blocked_fail_closed"] is True
    )
    status = STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED if recorded else STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_BLOCKED
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_RUNTIME_SUBMIT_ACTION_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_RUNTIME_SUBMIT_ACTION_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_RUNTIME_SUBMIT_ACTION_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe_sources.items())
    blockers.extend(validation.get("block_reasons", []))
    blockers.extend(readiness_validation.get("block_reasons", []))
    blockers.extend(RUNTIME_ACTION_BLOCKERS)
    report_id = stable_id("phase9_2_runtime_submit_action_boundary", {
        "template": template.get("phase9_2_runtime_submit_action_boundary_template_sha256"),
        "readiness": readiness.get("phase9_2_runtime_submit_action_readiness_report_sha256"),
    }, 24)
    report = {
        "phase9_2_runtime_submit_action_boundary_package_id": report_id,
        "phase9_2_runtime_submit_action_boundary_version": PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_VERSION,
        "status": status,
        "blocked": False if recorded else True,
        "fail_closed": False if recorded else True,
        "review_only": True,
        "still_disabled": True,
        "blocked_runtime_action_boundary": True,
        "phase9_2_runtime_submit_action_boundary_recorded": recorded,
        "runtime_submit_action_boundary_valid": recorded,
        "runtime_submit_action_ready_for_explicit_submit_approval_review_only": recorded,
        "runtime_submit_action_approved": False,
        "runtime_submit_action_executed": False,
        "runtime_submit_action_performed": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "actual_order_submission_performed": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe_sources,
        "runtime_submit_action_boundary_validation_report": validation,
        "runtime_submit_action_readiness_validation_report": readiness_validation,
        "negative_fixture_results": negative_results,
        "remaining_runtime_submit_blockers": RUNTIME_ACTION_BLOCKERS,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "recommended_next_action": "do_not_submit_order_until_explicit_runtime_submit_approval_and_fresh_endpoint_time_controls_are_applied_in_a_separate_action",
        **_disabled_payload(),
        "created_at_utc": created,
    }
    report["phase9_2_runtime_submit_action_boundary_report_sha256"] = sha256_json(report)
    return report, template, validation, readiness, readiness_validation, negative_results


def _handoff(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Phase 9.2 Runtime Submit Action Boundary - Blocked Review Only",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This artifact records the boundary immediately before any possible single signed testnet submit runtime action.",
        "It does not grant runtime authority and does not call order endpoints.",
        "",
        "## Still Disabled",
        "",
        "- `runtime_submit_action_approved=false`",
        "- `phase9_2_order_submission_authorized=false`",
        "- `actual_order_submission_performed=false`",
        "- `order_endpoint_called=false`",
        "- `http_request_sent=false`",
        "- `signature_created=false`",
        "",
    ])


def persist_phase9_2_runtime_submit_action_boundary_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_manual_confirmation_first: bool = True) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_runtime_submit_action_boundary")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, validation, readiness, readiness_validation, negative_results = build_phase9_2_runtime_submit_action_boundary_report(cfg=cfg, run_manual_confirmation_first=run_manual_confirmation_first)
    handoff = _handoff(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_runtime_submit_action_boundary_report.json", report)
        atomic_write_json(base / "phase9_2_runtime_submit_action_BOUNDARY_BLOCKED_REVIEW_ONLY.json", template)
        atomic_write_json(base / "phase9_2_runtime_submit_action_boundary_validation_report.json", validation)
        atomic_write_json(base / "phase9_2_runtime_submit_action_readiness_report.json", readiness)
        atomic_write_json(base / "phase9_2_runtime_submit_action_readiness_validation_report.json", readiness_validation)
        atomic_write_json(base / "phase9_2_runtime_submit_action_boundary_negative_fixture_results.json", negative_results)
        (base / "PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_HANDOFF_BLOCKED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_REGISTRY_NAME),
        {
            "phase9_2_runtime_submit_action_boundary_package_id": report.get("phase9_2_runtime_submit_action_boundary_package_id"),
            "status": report.get("status"),
            "phase9_2_runtime_submit_action_boundary_recorded": report.get("phase9_2_runtime_submit_action_boundary_recorded"),
            "runtime_submit_action_ready_for_explicit_submit_approval_review_only": report.get("runtime_submit_action_ready_for_explicit_submit_approval_review_only"),
            "runtime_submit_action_approved": False,
            "phase9_2_order_submission_authorized": False,
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_REGISTRY_NAME,
        id_field="phase9_2_runtime_submit_action_boundary_registry_record_id",
        hash_field="phase9_2_runtime_submit_action_boundary_registry_record_sha256",
        id_prefix="phase9_2_runtime_submit_action_boundary_registry_record",
    )
    atomic_write_json(latest / "phase9_2_runtime_submit_action_boundary_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_runtime_submit_action_boundary_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_VERSION",
    "STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED",
    "STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_BLOCKED",
    "build_runtime_submit_action_boundary_template",
    "validate_runtime_submit_action_boundary_template",
    "build_runtime_submit_action_readiness_report",
    "validate_runtime_submit_action_readiness_report",
    "build_phase9_2_runtime_submit_action_boundary_report",
    "persist_phase9_2_runtime_submit_action_boundary_report",
]
