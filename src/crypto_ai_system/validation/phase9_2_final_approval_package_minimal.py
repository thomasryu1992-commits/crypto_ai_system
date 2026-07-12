from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_executor_endpoint_policy_and_readiness import persist_phase9_2_executor_endpoint_policy_readiness_report
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool, _unsafe_fields

PHASE9_2_FINAL_APPROVAL_PACKAGE_VERSION = "phase9_2_final_approval_package_minimal_v1"
PHASE9_2_FINAL_APPROVAL_PACKAGE_REGISTRY_NAME = "phase9_2_final_approval_package_minimal_registry"
STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_VALID_STILL_DISABLED = "PHASE9_2_FINAL_APPROVAL_PACKAGE_VALID_STILL_DISABLED_REVIEW_ONLY"
STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_BLOCKED_STILL_DISABLED = "PHASE9_2_FINAL_APPROVAL_PACKAGE_BLOCKED_STILL_DISABLED_REVIEW_ONLY"

SOURCE_FILES = {
    "phase9_1_operator_fixture_validation": "phase9_1_operator_supplied_approval_fixture_validation_report.json",
    "phase9_2_submit_guard_recheck": "phase9_2_submit_guard_recheck_after_operator_fixture_report.json",
    "phase9_2_executor_endpoint_policy_readiness": "phase9_2_executor_endpoint_policy_readiness_report.json",
    "real_submit_readiness_packet": "real_submit_readiness_PACKET_STILL_DISABLED_REVIEW_ONLY.json",
}

REQUIRED_PACKET_FIELDS = [
    "phase9_2_final_approval_packet_id",
    "approval_scope",
    "operator_decision",
    "operator_signature_ref",
    "operator_approval_ticket_or_record_id",
    "testnet_only",
    "symbol",
    "max_order_count",
    "max_notional",
    "daily_loss_cap",
    "kill_switch_confirmed",
    "testnet_key_fingerprint_sha256",
    "fresh_risk_refresh_required",
    "idempotency_required",
    "duplicate_submit_lock_required",
    "phase9_2_order_submission_authorized",
]

REQUIRED_READINESS_FIELDS = [
    "phase9_2_final_submit_readiness_report_id",
    "source_final_approval_packet_hash",
    "source_final_approval_validation_hash",
    "final_approval_packet_valid",
    "phase9_2_ready_for_manual_final_confirmation",
    "phase9_2_order_submission_authorized",
    "actual_order_submission_performed",
]

REMAINING_FINAL_APPROVAL_BLOCKERS = [
    "PHASE9_2_FINAL_APPROVAL_REQUIRES_REAL_OPERATOR_APPROVAL_RECORD_NOT_FIXTURE_BEFORE_RUNTIME_SUBMIT",
    "PHASE9_2_FINAL_APPROVAL_REQUIRES_ACTUAL_ENDPOINT_TIME_RISK_REFRESH_AT_SUBMIT_MOMENT",
    "PHASE9_2_FINAL_APPROVAL_REQUIRES_SECRET_MANAGER_RUNTIME_BINDING_APPLICATION_NOT_PRESENT",
    "PHASE9_2_FINAL_APPROVAL_REQUIRES_EXECUTOR_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_FINAL_APPROVAL_REQUIRES_ENDPOINT_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_FINAL_APPROVAL_DOES_NOT_CREATE_SIGNATURE_HTTP_OR_ORDER_ENDPOINT_CALL",
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
        "phase9_1_operator_supplied_approval_fixture_validation_report_sha256",
        "phase9_2_submit_guard_recheck_report_sha256",
        "phase9_2_executor_endpoint_policy_readiness_report_sha256",
        "phase9_2_real_submit_readiness_packet_sha256",
        "phase9_2_final_approval_packet_sha256",
        "phase9_2_final_approval_validation_report_sha256",
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
    if name == "phase9_1_operator_fixture_validation":
        return data.get("fixture_valid_review_only") is True and data.get("phase9_2_submit_guard_recheck_may_begin") is True
    if name == "phase9_2_submit_guard_recheck":
        return data.get("phase9_2_submit_guard_recheck_ready") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_executor_endpoint_policy_readiness":
        return data.get("real_submit_readiness_packet_ready_for_manual_review") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "real_submit_readiness_packet":
        return data.get("real_submit_readiness_packet_complete") is True and data.get("phase9_2_order_submission_authorized") is False
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


def build_final_approval_packet_template(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    fixture_validation = dict(sources.get("phase9_1_operator_fixture_validation") or {})
    fixture_validator = dict(fixture_validation.get("validator_result") or {})
    recheck = dict(sources.get("phase9_2_submit_guard_recheck") or {})
    readiness = dict(sources.get("phase9_2_executor_endpoint_policy_readiness") or {})
    packet_id = stable_id("phase9_2_final_approval_packet_minimal", {
        "fixture": _hash(fixture_validation),
        "recheck": _hash(recheck),
        "readiness": _hash(readiness),
    }, 24)
    packet = {
        "artifact_type": "phase9_2_final_approval_packet_template_still_disabled_review_only",
        "phase9_2_final_approval_packet_id": packet_id,
        "phase9_2_final_approval_packet_version": PHASE9_2_FINAL_APPROVAL_PACKAGE_VERSION,
        "review_only": True,
        "still_disabled": True,
        "approval_scope": "single_signed_testnet_order_only",
        "operator_decision": "approve_single_signed_testnet_order",
        "operator_signature_ref": "operator_signature_hash_sha256_metadata_only",
        "operator_approval_ticket_or_record_id": "operator_supplied_approval_fixture_record_review_only",
        "operator_approval_is_fixture_only": True,
        "operator_real_approval_required_before_runtime_submit": True,
        "operator_approval_real_not_fixture": False,
        "source_phase9_1_operator_fixture_validation_hash": _hash(fixture_validation),
        "source_phase9_2_submit_guard_recheck_hash": _hash(recheck),
        "source_phase9_2_executor_endpoint_policy_readiness_hash": _hash(readiness),
        "testnet_only": True,
        "symbol": "BTCUSDT",
        "max_order_count": 1,
        "max_notional": float(fixture_validator.get("small_max_notional") or 10.0),
        "daily_loss_cap": float(fixture_validator.get("daily_loss_cap") or 15.0),
        "kill_switch_confirmed": True,
        "testnet_key_fingerprint_sha256": "metadata_only_testnet_key_fingerprint_present_in_validated_fixture",
        "fresh_risk_refresh_required": True,
        "idempotency_required": True,
        "duplicate_submit_lock_required": True,
        "cancel_plan_required": True,
        "status_polling_plan_required": True,
        "reconciliation_plan_required": True,
        "phase9_2_final_approval_packet_valid_for_manual_confirmation_review": True,
        **_disabled_payload(),
    }
    packet["phase9_2_final_approval_packet_sha256"] = sha256_json(packet)
    return packet


def validate_final_approval_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(packet or {})
    blockers: list[str] = []
    blockers.extend(f"PHASE9_2_FINAL_APPROVAL_PACKET_MISSING_FIELD:{field}" for field in REQUIRED_PACKET_FIELDS if field not in data)
    if data.get("artifact_type") != "phase9_2_final_approval_packet_template_still_disabled_review_only":
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_NOT_STILL_DISABLED_REVIEW_ONLY")
    if data.get("approval_scope") != "single_signed_testnet_order_only":
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_INVALID_SCOPE")
    if data.get("operator_decision") != "approve_single_signed_testnet_order":
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_OPERATOR_DECISION_NOT_APPROVE_SINGLE_ORDER")
    if not str(data.get("operator_signature_ref") or "").strip():
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_OPERATOR_SIGNATURE_REF_MISSING")
    if not str(data.get("operator_approval_ticket_or_record_id") or "").strip():
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_OPERATOR_APPROVAL_TICKET_MISSING")
    if not str(data.get("testnet_key_fingerprint_sha256") or "").strip():
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_TESTNET_KEY_FINGERPRINT_MISSING")
    if data.get("operator_approval_is_fixture_only") is not True:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_FIXTURE_BOUNDARY_NOT_EXPLICIT")
    if data.get("operator_real_approval_required_before_runtime_submit") is not True:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_REAL_APPROVAL_NOT_REQUIRED")
    if data.get("max_order_count") != 1:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_MAX_ORDER_COUNT_NOT_ONE")
    if float(data.get("max_notional") or 0) > 10.0:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_MAX_NOTIONAL_TOO_LARGE")
    if float(data.get("daily_loss_cap") or 0) > 15.0:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_DAILY_LOSS_CAP_TOO_LARGE")
    for field in ["testnet_only", "kill_switch_confirmed", "fresh_risk_refresh_required", "idempotency_required", "duplicate_submit_lock_required", "cancel_plan_required", "status_polling_plan_required", "reconciliation_plan_required"]:
        if data.get(field) is not True:
            blockers.append(f"PHASE9_2_FINAL_APPROVAL_PACKET_REQUIRED_TRUE_FIELD_FALSE:{field}")
    for field in ["phase9_2_order_submission_authorized", "actual_order_submission_performed", "order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created", "signed_order_executor_enabled", "place_order_enabled", "cancel_order_enabled"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_FINAL_APPROVAL_PACKET_UNSAFE_FLAG:{field}")
    unsafe = _unsafe_runtime_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_UNSAFE_FIELDS:" + ",".join(unsafe))
    secret_like = [path for path in _find_secret_like_values(data) if "hash" not in path.lower() and "sha256" not in path.lower() and "fingerprint" not in path.lower() and "metadata" not in path.lower()]
    if secret_like:
        blockers.append("PHASE9_2_FINAL_APPROVAL_PACKET_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like))
    valid = not blockers
    report = {
        "artifact_type": "phase9_2_final_approval_validation_report",
        "phase9_2_final_approval_packet_valid": valid,
        "final_approval_packet_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "operator_approval_real_not_fixture": False,
        "operator_real_approval_required_before_runtime_submit": True,
        "single_order_scope_valid": data.get("max_order_count") == 1,
        "testnet_only_key_fingerprint_present": bool(data.get("testnet_key_fingerprint_sha256")),
        "max_order_count_valid": data.get("max_order_count") == 1,
        "max_notional_valid": float(data.get("max_notional") or 0) <= 10.0,
        "kill_switch_confirmed": data.get("kill_switch_confirmed") is True,
        "idempotency_required": data.get("idempotency_required") is True,
        "duplicate_submit_lock_required": data.get("duplicate_submit_lock_required") is True,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_disabled_payload(),
    }
    report["phase9_2_final_approval_validation_report_sha256"] = sha256_json(report)
    return report


def build_final_submit_readiness_report(packet: Mapping[str, Any], validation: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    report_id = stable_id("phase9_2_final_submit_readiness_report", {
        "packet": _hash(packet),
        "validation": _hash(validation),
        "recheck": _hash(sources.get("phase9_2_submit_guard_recheck") or {}),
        "readiness": _hash(sources.get("phase9_2_executor_endpoint_policy_readiness") or {}),
    }, 24)
    packet_valid = dict(validation).get("final_approval_packet_valid") is True
    report = {
        "artifact_type": "phase9_2_final_submit_readiness_report_still_disabled_review_only",
        "phase9_2_final_submit_readiness_report_id": report_id,
        "version": PHASE9_2_FINAL_APPROVAL_PACKAGE_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_final_approval_packet_hash": _hash(packet),
        "source_final_approval_validation_hash": _hash(validation),
        "source_phase9_2_submit_guard_recheck_hash": _hash(sources.get("phase9_2_submit_guard_recheck") or {}),
        "source_phase9_2_executor_endpoint_policy_readiness_hash": _hash(sources.get("phase9_2_executor_endpoint_policy_readiness") or {}),
        "final_approval_packet_exists": bool(packet),
        "final_approval_packet_valid": packet_valid,
        "single_order_scope_valid": dict(validation).get("single_order_scope_valid") is True,
        "testnet_only_key_fingerprint_present": dict(validation).get("testnet_only_key_fingerprint_present") is True,
        "risk_refresh_required": True,
        "idempotency_ready": True,
        "duplicate_submit_lock_ready": True,
        "status_polling_plan_ready": True,
        "cancel_plan_ready": True,
        "reconciliation_plan_ready": True,
        "phase9_2_ready_for_manual_final_confirmation": packet_valid,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "remaining_real_submit_blockers": REMAINING_FINAL_APPROVAL_BLOCKERS,
        **_disabled_payload(),
    }
    report["phase9_2_final_submit_readiness_report_sha256"] = sha256_json(report)
    return report


def validate_final_submit_readiness_report(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    blockers: list[str] = []
    blockers.extend(f"PHASE9_2_FINAL_SUBMIT_READINESS_MISSING_FIELD:{field}" for field in REQUIRED_READINESS_FIELDS if field not in data)
    if data.get("artifact_type") != "phase9_2_final_submit_readiness_report_still_disabled_review_only":
        blockers.append("PHASE9_2_FINAL_SUBMIT_READINESS_INVALID_ARTIFACT_TYPE")
    if data.get("final_approval_packet_valid") is not True:
        blockers.append("PHASE9_2_FINAL_SUBMIT_READINESS_FINAL_APPROVAL_INVALID")
    if data.get("phase9_2_ready_for_manual_final_confirmation") is not True:
        blockers.append("PHASE9_2_FINAL_SUBMIT_READINESS_NOT_READY_FOR_MANUAL_CONFIRMATION")
    for field in ["phase9_2_order_submission_authorized", "actual_order_submission_performed", "order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_FINAL_SUBMIT_READINESS_UNSAFE_FLAG:{field}")
    unsafe = _unsafe_runtime_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_FINAL_SUBMIT_READINESS_UNSAFE_FIELDS:" + ",".join(unsafe))
    valid = not blockers
    validation = {
        "artifact_type": "phase9_2_final_submit_readiness_validation_report",
        "phase9_2_final_submit_readiness_report_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "unsafe_truthy_fields": unsafe,
        **_disabled_payload(),
    }
    validation["phase9_2_final_submit_readiness_validation_report_sha256"] = sha256_json(validation)
    return validation


def _negative_fixture_results(packet: Mapping[str, Any], readiness: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, tuple[str, Mapping[str, Any], Any]] = {
        "missing_operator_signature_ref": ("packet", {"operator_signature_ref": ""}, validate_final_approval_packet),
        "max_order_count_gt_one": ("packet", {"max_order_count": 2}, validate_final_approval_packet),
        "max_notional_too_large": ("packet", {"max_notional": 100.0}, validate_final_approval_packet),
        "raw_secret_value_present": ("packet", {"api_secret": "raw-secret-value-should-block"}, validate_final_approval_packet),
        "order_endpoint_called_true": ("readiness", {"order_endpoint_called": True}, validate_final_submit_readiness_report),
        "http_request_sent_true": ("readiness", {"http_request_sent": True}, validate_final_submit_readiness_report),
        "signature_created_true": ("readiness", {"signature_created": True}, validate_final_submit_readiness_report),
        "order_submission_authorized_true": ("readiness", {"phase9_2_order_submission_authorized": True}, validate_final_submit_readiness_report),
    }
    base = {"packet": dict(packet), "readiness": dict(readiness)}
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
        "artifact_type": "phase9_2_final_approval_package_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] and item["fail_closed"] for item in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
    }


def build_phase9_2_final_approval_package_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_readiness_first: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    if run_readiness_first:
        persist_phase9_2_executor_endpoint_policy_readiness_report(cfg=cfg, run_secret_binding_first=True)
    created = utc_now_canonical()
    sources = {name: _read_latest_json(cfg, filename) for name, filename in SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe_sources = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    packet = build_final_approval_packet_template(sources)
    validation = validate_final_approval_packet(packet)
    readiness = build_final_submit_readiness_report(packet, validation, sources)
    readiness_validation = validate_final_submit_readiness_report(readiness)
    negative_results = _negative_fixture_results(packet, readiness)
    recorded = (
        not missing
        and not not_ready
        and not unsafe_sources
        and validation["final_approval_packet_valid"] is True
        and readiness_validation["phase9_2_final_submit_readiness_report_valid"] is True
        and negative_results["all_negative_fixtures_blocked_fail_closed"] is True
    )
    status = STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_VALID_STILL_DISABLED if recorded else STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_BLOCKED_STILL_DISABLED
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_FINAL_APPROVAL_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_FINAL_APPROVAL_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_FINAL_APPROVAL_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe_sources.items())
    blockers.extend(validation.get("block_reasons", []))
    blockers.extend(readiness_validation.get("block_reasons", []))
    blockers.extend(REMAINING_FINAL_APPROVAL_BLOCKERS)
    report_id = stable_id("phase9_2_final_approval_package_minimal", {
        "packet": packet.get("phase9_2_final_approval_packet_sha256"),
        "readiness": readiness.get("phase9_2_final_submit_readiness_report_sha256"),
    }, 24)
    report = {
        "phase9_2_final_approval_package_id": report_id,
        "phase9_2_final_approval_package_version": PHASE9_2_FINAL_APPROVAL_PACKAGE_VERSION,
        "status": status,
        "blocked": False if recorded else True,
        "fail_closed": False if recorded else True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_final_approval_package_recorded": recorded,
        "final_approval_packet_exists": True,
        "final_approval_packet_valid": recorded,
        "phase9_2_ready_for_manual_final_confirmation": recorded,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe_sources,
        "final_approval_validation_report": validation,
        "final_submit_readiness_validation_report": readiness_validation,
        "negative_fixture_results": negative_results,
        "remaining_real_submit_blockers": REMAINING_FINAL_APPROVAL_BLOCKERS,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "recommended_next_action": "create_manual_final_confirmation_package_or_keep_phase9_2_order_submission_disabled_until_separate_real_runtime_authority_is_granted",
        **_disabled_payload(),
        "created_at_utc": created,
    }
    report["phase9_2_final_approval_package_report_sha256"] = sha256_json(report)
    return report, packet, validation, readiness, readiness_validation, negative_results


def _handoff(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Phase 9.2 Final Approval Package Minimal - Still Disabled",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This minimal package consolidates the validated Phase 9.1 operator approval fixture, Phase 9.2 submit guard recheck, and executor/endpoint readiness evidence into a final approval package for manual final confirmation review.",
        "",
        "It does not grant runtime authority, perform secret binding, apply executor policy, apply endpoint policy, create signatures, send HTTP requests, call order endpoints, or submit orders.",
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


def persist_phase9_2_final_approval_package_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_readiness_first: bool = True) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_final_approval_package_minimal")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, packet, validation, readiness, readiness_validation, negative_results = build_phase9_2_final_approval_package_report(cfg=cfg, run_readiness_first=run_readiness_first)
    handoff = _handoff(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_final_approval_package_report.json", report)
        atomic_write_json(base / "phase9_2_final_approval_packet_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json", packet)
        atomic_write_json(base / "phase9_2_final_approval_validation_report.json", validation)
        atomic_write_json(base / "phase9_2_final_submit_readiness_report.json", readiness)
        atomic_write_json(base / "phase9_2_final_submit_readiness_validation_report.json", readiness_validation)
        atomic_write_json(base / "phase9_2_final_approval_package_negative_fixture_results.json", negative_results)
        (base / "PHASE9_2_FINAL_APPROVAL_PACKAGE_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_FINAL_APPROVAL_PACKAGE_REGISTRY_NAME),
        {
            "phase9_2_final_approval_package_id": report.get("phase9_2_final_approval_package_id"),
            "status": report.get("status"),
            "phase9_2_final_approval_package_recorded": report.get("phase9_2_final_approval_package_recorded"),
            "final_approval_packet_valid": report.get("final_approval_packet_valid"),
            "phase9_2_ready_for_manual_final_confirmation": report.get("phase9_2_ready_for_manual_final_confirmation"),
            "phase9_2_order_submission_authorized": False,
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_FINAL_APPROVAL_PACKAGE_REGISTRY_NAME,
        id_field="phase9_2_final_approval_package_registry_record_id",
        hash_field="phase9_2_final_approval_package_registry_record_sha256",
        id_prefix="phase9_2_final_approval_package_registry_record",
    )
    atomic_write_json(latest / "phase9_2_final_approval_package_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_final_approval_package_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_FINAL_APPROVAL_PACKAGE_VERSION",
    "STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_VALID_STILL_DISABLED",
    "STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_BLOCKED_STILL_DISABLED",
    "build_final_approval_packet_template",
    "validate_final_approval_packet",
    "build_final_submit_readiness_report",
    "validate_final_submit_readiness_report",
    "build_phase9_2_final_approval_package_report",
    "persist_phase9_2_final_approval_package_report",
]
