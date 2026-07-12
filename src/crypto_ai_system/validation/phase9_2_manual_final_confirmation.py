
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_final_approval_package_minimal import persist_phase9_2_final_approval_package_report
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool, _unsafe_fields

PHASE9_2_MANUAL_FINAL_CONFIRMATION_VERSION = "phase9_2_manual_final_confirmation_v1"
PHASE9_2_MANUAL_FINAL_CONFIRMATION_REGISTRY_NAME = "phase9_2_manual_final_confirmation_registry"
STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_VALID_STILL_DISABLED = "PHASE9_2_MANUAL_FINAL_CONFIRMATION_VALID_STILL_DISABLED_REVIEW_ONLY"
STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_BLOCKED_STILL_DISABLED = "PHASE9_2_MANUAL_FINAL_CONFIRMATION_BLOCKED_STILL_DISABLED_REVIEW_ONLY"

SOURCE_FILES = {
    "phase9_2_final_approval_package": "phase9_2_final_approval_package_report.json",
    "phase9_2_final_approval_validation": "phase9_2_final_approval_validation_report.json",
    "phase9_2_final_submit_readiness": "phase9_2_final_submit_readiness_report.json",
}

REQUIRED_CONFIRMATION_FIELDS = [
    "phase9_2_manual_final_confirmation_id",
    "confirmation_scope",
    "confirm_single_order_only",
    "confirm_testnet_only",
    "confirm_max_notional_reviewed",
    "confirm_kill_switch_ready",
    "confirm_no_mainnet_key",
    "confirm_no_withdrawal_permission",
    "confirm_fresh_risk_refresh_required",
    "confirm_order_payload_reviewed",
    "confirm_idempotency_key_reviewed",
    "confirm_duplicate_submit_lock_ready",
    "confirm_status_polling_plan_ready",
    "confirm_cancel_plan_ready",
    "confirm_reconciliation_plan_ready",
    "phase9_2_manual_final_confirmation_ready_for_separate_submit_action",
    "phase9_2_order_submission_authorized",
]

REMAINING_MANUAL_CONFIRMATION_BLOCKERS = [
    "PHASE9_2_MANUAL_CONFIRMATION_REQUIRES_SEPARATE_REAL_SUBMIT_ACTION_AFTER_CONFIRMATION",
    "PHASE9_2_MANUAL_CONFIRMATION_REQUIRES_FRESH_ENDPOINT_TIME_RISK_REFRESH_AT_SUBMIT_MOMENT",
    "PHASE9_2_MANUAL_CONFIRMATION_REQUIRES_RUNTIME_SECRET_BINDING_OUTSIDE_REVIEW_ARTIFACTS",
    "PHASE9_2_MANUAL_CONFIRMATION_REQUIRES_EXECUTOR_AND_ENDPOINT_POLICY_APPLICATION_OUTSIDE_THIS_PACKAGE",
    "PHASE9_2_MANUAL_CONFIRMATION_DOES_NOT_CREATE_SIGNATURE_HTTP_OR_ORDER_ENDPOINT_CALL",
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


def _hash(payload: Mapping[str, Any]) -> str:
    data = dict(payload or {})
    for key in [
        "phase9_2_final_approval_package_report_sha256",
        "phase9_2_final_approval_validation_report_sha256",
        "phase9_2_final_submit_readiness_report_sha256",
        "phase9_2_manual_final_confirmation_template_sha256",
        "phase9_2_manual_final_confirmation_validation_report_sha256",
    ]:
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


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
    if name == "phase9_2_final_approval_package":
        return data.get("phase9_2_final_approval_package_recorded") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_final_approval_validation":
        return data.get("final_approval_packet_valid") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_final_submit_readiness":
        return data.get("phase9_2_ready_for_manual_final_confirmation") is True and data.get("phase9_2_order_submission_authorized") is False
    return True


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
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
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


def build_manual_final_confirmation_template(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    final_pkg = dict(sources.get("phase9_2_final_approval_package") or {})
    readiness = dict(sources.get("phase9_2_final_submit_readiness") or {})
    confirmation_id = stable_id("phase9_2_manual_final_confirmation", {
        "final_pkg": _hash(final_pkg),
        "readiness": _hash(readiness),
    }, 24)
    payload = {
        "artifact_type": "phase9_2_manual_final_confirmation_template_still_disabled_review_only",
        "phase9_2_manual_final_confirmation_id": confirmation_id,
        "phase9_2_manual_final_confirmation_version": PHASE9_2_MANUAL_FINAL_CONFIRMATION_VERSION,
        "review_only": True,
        "still_disabled": True,
        "confirmation_scope": "single_signed_testnet_order_manual_final_confirmation_only",
        "source_phase9_2_final_approval_package_hash": _hash(final_pkg),
        "source_phase9_2_final_submit_readiness_hash": _hash(readiness),
        "confirm_single_order_only": True,
        "confirm_testnet_only": True,
        "confirm_max_notional_reviewed": True,
        "confirm_kill_switch_ready": True,
        "confirm_no_mainnet_key": True,
        "confirm_no_withdrawal_permission": True,
        "confirm_fresh_risk_refresh_required": True,
        "confirm_order_payload_reviewed": True,
        "confirm_idempotency_key_reviewed": True,
        "confirm_duplicate_submit_lock_ready": True,
        "confirm_status_polling_plan_ready": True,
        "confirm_cancel_plan_ready": True,
        "confirm_reconciliation_plan_ready": True,
        "manual_final_confirmation_is_review_only": True,
        "manual_final_confirmation_is_not_runtime_submit_authority": True,
        "phase9_2_manual_final_confirmation_ready_for_separate_submit_action": True,
        **_disabled_payload(),
    }
    payload["phase9_2_manual_final_confirmation_template_sha256"] = sha256_json(payload)
    return payload


def validate_manual_final_confirmation_template(template: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(template or {})
    blockers: list[str] = []
    blockers.extend(f"PHASE9_2_MANUAL_CONFIRMATION_MISSING_FIELD:{field}" for field in REQUIRED_CONFIRMATION_FIELDS if field not in data)
    if data.get("artifact_type") != "phase9_2_manual_final_confirmation_template_still_disabled_review_only":
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_NOT_STILL_DISABLED_REVIEW_ONLY")
    if data.get("confirmation_scope") != "single_signed_testnet_order_manual_final_confirmation_only":
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_INVALID_SCOPE")
    for field in [
        "confirm_single_order_only",
        "confirm_testnet_only",
        "confirm_max_notional_reviewed",
        "confirm_kill_switch_ready",
        "confirm_no_mainnet_key",
        "confirm_no_withdrawal_permission",
        "confirm_fresh_risk_refresh_required",
        "confirm_order_payload_reviewed",
        "confirm_idempotency_key_reviewed",
        "confirm_duplicate_submit_lock_ready",
        "confirm_status_polling_plan_ready",
        "confirm_cancel_plan_ready",
        "confirm_reconciliation_plan_ready",
        "manual_final_confirmation_is_review_only",
        "manual_final_confirmation_is_not_runtime_submit_authority",
    ]:
        if data.get(field) is not True:
            blockers.append(f"PHASE9_2_MANUAL_CONFIRMATION_REQUIRED_TRUE_FIELD_FALSE:{field}")
    for field in ["phase9_2_order_submission_authorized", "actual_order_submission_performed", "order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created", "signed_order_executor_enabled", "place_order_enabled", "cancel_order_enabled"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_MANUAL_CONFIRMATION_UNSAFE_FLAG:{field}")
    unsafe = _unsafe_runtime_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_UNSAFE_FIELDS:" + ",".join(unsafe))
    secret_like = [path for path in _find_secret_like_values(data) if "hash" not in path.lower() and "sha256" not in path.lower() and "fingerprint" not in path.lower() and "metadata" not in path.lower()]
    if secret_like:
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like))
    valid = not blockers
    report = {
        "artifact_type": "phase9_2_manual_final_confirmation_validation_report",
        "phase9_2_manual_final_confirmation_template_valid": valid,
        "manual_final_confirmation_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "manual_final_confirmation_is_review_only": True,
        "manual_final_confirmation_is_not_runtime_submit_authority": True,
        "phase9_2_manual_final_confirmation_ready_for_separate_submit_action": valid,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_disabled_payload(),
    }
    report["phase9_2_manual_final_confirmation_validation_report_sha256"] = sha256_json(report)
    return report


def build_manual_final_confirmation_readiness_report(template: Mapping[str, Any], validation: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ready = dict(validation).get("manual_final_confirmation_valid") is True
    report_id = stable_id("phase9_2_manual_final_confirmation_readiness", {
        "template": _hash(template),
        "validation": _hash(validation),
        "final_pkg": _hash(sources.get("phase9_2_final_approval_package") or {}),
    }, 24)
    report = {
        "artifact_type": "phase9_2_manual_final_confirmation_readiness_report_still_disabled_review_only",
        "phase9_2_manual_final_confirmation_readiness_report_id": report_id,
        "version": PHASE9_2_MANUAL_FINAL_CONFIRMATION_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_manual_final_confirmation_template_hash": _hash(template),
        "source_manual_final_confirmation_validation_hash": _hash(validation),
        "source_final_approval_package_hash": _hash(sources.get("phase9_2_final_approval_package") or {}),
        "manual_final_confirmation_valid": ready,
        "manual_final_confirmation_ready": ready,
        "phase9_2_ready_for_separate_submit_action_review_only": ready,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "remaining_real_submit_blockers": REMAINING_MANUAL_CONFIRMATION_BLOCKERS,
        **_disabled_payload(),
    }
    report["phase9_2_manual_final_confirmation_readiness_report_sha256"] = sha256_json(report)
    return report


def validate_manual_final_confirmation_readiness_report(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    blockers: list[str] = []
    if data.get("artifact_type") != "phase9_2_manual_final_confirmation_readiness_report_still_disabled_review_only":
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_READINESS_INVALID_ARTIFACT_TYPE")
    if data.get("manual_final_confirmation_ready") is not True:
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_READINESS_NOT_READY")
    for field in ["phase9_2_order_submission_authorized", "actual_order_submission_performed", "order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_MANUAL_CONFIRMATION_READINESS_UNSAFE_FLAG:{field}")
    unsafe = _unsafe_runtime_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_MANUAL_CONFIRMATION_READINESS_UNSAFE_FIELDS:" + ",".join(unsafe))
    valid = not blockers
    validation = {
        "artifact_type": "phase9_2_manual_final_confirmation_readiness_validation_report",
        "phase9_2_manual_final_confirmation_readiness_report_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "unsafe_truthy_fields": unsafe,
        **_disabled_payload(),
    }
    validation["phase9_2_manual_final_confirmation_readiness_validation_report_sha256"] = sha256_json(validation)
    return validation


def _negative_fixture_results(template: Mapping[str, Any], readiness: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, tuple[str, Mapping[str, Any], Any]] = {
        "missing_kill_switch_confirmation": ("template", {"confirm_kill_switch_ready": False}, validate_manual_final_confirmation_template),
        "missing_testnet_only_confirmation": ("template", {"confirm_testnet_only": False}, validate_manual_final_confirmation_template),
        "missing_cancel_plan_confirmation": ("template", {"confirm_cancel_plan_ready": False}, validate_manual_final_confirmation_template),
        "missing_reconciliation_plan_confirmation": ("template", {"confirm_reconciliation_plan_ready": False}, validate_manual_final_confirmation_template),
        "order_submission_authorized_true": ("readiness", {"phase9_2_order_submission_authorized": True}, validate_manual_final_confirmation_readiness_report),
        "order_endpoint_called_true": ("readiness", {"order_endpoint_called": True}, validate_manual_final_confirmation_readiness_report),
        "http_request_sent_true": ("readiness", {"http_request_sent": True}, validate_manual_final_confirmation_readiness_report),
        "signature_created_true": ("readiness", {"signature_created": True}, validate_manual_final_confirmation_readiness_report),
        "raw_secret_value_present": ("template", {"api_secret": "raw-secret-value-should-block"}, validate_manual_final_confirmation_template),
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
        "artifact_type": "phase9_2_manual_final_confirmation_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] and item["fail_closed"] for item in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
    }


def build_phase9_2_manual_final_confirmation_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_final_approval_first: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    if run_final_approval_first:
        persist_phase9_2_final_approval_package_report(cfg=cfg, run_readiness_first=True)
    created = utc_now_canonical()
    sources = {name: _read_latest_json(cfg, filename) for name, filename in SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe_sources = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    template = build_manual_final_confirmation_template(sources)
    validation = validate_manual_final_confirmation_template(template)
    readiness = build_manual_final_confirmation_readiness_report(template, validation, sources)
    readiness_validation = validate_manual_final_confirmation_readiness_report(readiness)
    negative_results = _negative_fixture_results(template, readiness)
    recorded = (
        not missing
        and not not_ready
        and not unsafe_sources
        and validation["manual_final_confirmation_valid"] is True
        and readiness_validation["phase9_2_manual_final_confirmation_readiness_report_valid"] is True
        and negative_results["all_negative_fixtures_blocked_fail_closed"] is True
    )
    status = STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_VALID_STILL_DISABLED if recorded else STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_BLOCKED_STILL_DISABLED
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_MANUAL_CONFIRMATION_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_MANUAL_CONFIRMATION_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_MANUAL_CONFIRMATION_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe_sources.items())
    blockers.extend(validation.get("block_reasons", []))
    blockers.extend(readiness_validation.get("block_reasons", []))
    blockers.extend(REMAINING_MANUAL_CONFIRMATION_BLOCKERS)
    report_id = stable_id("phase9_2_manual_final_confirmation", {
        "template": template.get("phase9_2_manual_final_confirmation_template_sha256"),
        "readiness": readiness.get("phase9_2_manual_final_confirmation_readiness_report_sha256"),
    }, 24)
    report = {
        "phase9_2_manual_final_confirmation_package_id": report_id,
        "phase9_2_manual_final_confirmation_version": PHASE9_2_MANUAL_FINAL_CONFIRMATION_VERSION,
        "status": status,
        "blocked": False if recorded else True,
        "fail_closed": False if recorded else True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_manual_final_confirmation_recorded": recorded,
        "manual_final_confirmation_valid": recorded,
        "phase9_2_ready_for_separate_submit_action_review_only": recorded,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe_sources,
        "manual_final_confirmation_validation_report": validation,
        "manual_final_confirmation_readiness_validation_report": readiness_validation,
        "negative_fixture_results": negative_results,
        "remaining_real_submit_blockers": REMAINING_MANUAL_CONFIRMATION_BLOCKERS,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "recommended_next_action": "keep_order_submission_disabled_or_create_separate_runtime_submit_action_with_fresh_endpoint_time_risk_refresh_and_secret_binding_outside_review_artifacts",
        **_disabled_payload(),
        "created_at_utc": created,
    }
    report["phase9_2_manual_final_confirmation_report_sha256"] = sha256_json(report)
    return report, template, validation, readiness, readiness_validation, negative_results


def _handoff(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Phase 9.2 Manual Final Confirmation - Still Disabled",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This package records the final manual confirmation checklist after the final approval package. It confirms that the next possible action would require a separate runtime submit action, fresh endpoint-time risk refresh, runtime secret binding, and executor/endpoint policy application outside review artifacts.",
        "",
        "It does not authorize or perform order submission.",
        "",
        "## Still Disabled",
        "",
        "- `phase9_2_order_submission_authorized=false`",
        "- `actual_order_submission_performed=false`",
        "- `order_endpoint_called=false`",
        "- `http_request_sent=false`",
        "- `signature_created=false`",
        "",
    ])


def persist_phase9_2_manual_final_confirmation_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_final_approval_first: bool = True) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_manual_final_confirmation")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, validation, readiness, readiness_validation, negative_results = build_phase9_2_manual_final_confirmation_report(cfg=cfg, run_final_approval_first=run_final_approval_first)
    handoff = _handoff(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_manual_final_confirmation_report.json", report)
        atomic_write_json(base / "phase9_2_manual_final_confirmation_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json", template)
        atomic_write_json(base / "phase9_2_manual_final_confirmation_validation_report.json", validation)
        atomic_write_json(base / "phase9_2_manual_final_confirmation_readiness_report.json", readiness)
        atomic_write_json(base / "phase9_2_manual_final_confirmation_readiness_validation_report.json", readiness_validation)
        atomic_write_json(base / "phase9_2_manual_final_confirmation_negative_fixture_results.json", negative_results)
        (base / "PHASE9_2_MANUAL_FINAL_CONFIRMATION_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_MANUAL_FINAL_CONFIRMATION_REGISTRY_NAME),
        {
            "phase9_2_manual_final_confirmation_package_id": report.get("phase9_2_manual_final_confirmation_package_id"),
            "status": report.get("status"),
            "phase9_2_manual_final_confirmation_recorded": report.get("phase9_2_manual_final_confirmation_recorded"),
            "manual_final_confirmation_valid": report.get("manual_final_confirmation_valid"),
            "phase9_2_ready_for_separate_submit_action_review_only": report.get("phase9_2_ready_for_separate_submit_action_review_only"),
            "phase9_2_order_submission_authorized": False,
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_MANUAL_FINAL_CONFIRMATION_REGISTRY_NAME,
        id_field="phase9_2_manual_final_confirmation_registry_record_id",
        hash_field="phase9_2_manual_final_confirmation_registry_record_sha256",
        id_prefix="phase9_2_manual_final_confirmation_registry_record",
    )
    atomic_write_json(latest / "phase9_2_manual_final_confirmation_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_manual_final_confirmation_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_MANUAL_FINAL_CONFIRMATION_VERSION",
    "STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_VALID_STILL_DISABLED",
    "STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_BLOCKED_STILL_DISABLED",
    "build_manual_final_confirmation_template",
    "validate_manual_final_confirmation_template",
    "build_manual_final_confirmation_readiness_report",
    "validate_manual_final_confirmation_readiness_report",
    "build_phase9_2_manual_final_confirmation_report",
    "persist_phase9_2_manual_final_confirmation_report",
]
