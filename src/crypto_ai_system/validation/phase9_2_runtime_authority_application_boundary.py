from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import (
    _artifact_hash,
    _find_secret_like_values,
    _flag_false_payload,
    _safe_bool,
    _unsafe_fields,
)
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request_validator import (
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED,
    validate_operator_filled_runtime_authority_change_request,
    persist_phase9_2_runtime_authority_change_request_validator_report,
)

PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_VERSION = "phase9_2_runtime_authority_application_boundary_v1"
PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_REGISTRY_NAME = "phase9_2_runtime_authority_application_boundary_registry"
STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED = (
    "PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED_REVIEW_ONLY"
)
STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_BLOCKED_REVIEW_ONLY = (
    "PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_BLOCKED_REVIEW_ONLY"
)

REQUIRED_SOURCE_FILES = {
    "phase9_2_runtime_authority_change_request_validator_report": "phase9_2_runtime_authority_change_request_validator_report.json",
    "phase9_2_runtime_authority_operator_filled_fixture": "runtime_authority_change_request_OPERATOR_FILLED_FIXTURE_STILL_DISABLED_REVIEW_ONLY.json",
    "phase9_2_runtime_authority_operator_values_validation": "phase9_2_runtime_authority_change_request_operator_values_validation_report.json",
    "phase9_2_runtime_authority_change_request_report": "phase9_2_runtime_authority_change_request_report.json",
    "phase9_2_runtime_authority_bridge_report": "phase9_2_runtime_authority_bridge_report.json",
    "phase9_2_real_submit_gate_report": "phase9_2_real_submit_enablement_gate_report.json",
    "phase8_3_hot_path_risk_gate_report": "phase8_3_hot_path_preorder_risk_gate_report.json",
    "phase8_4_signed_testnet_executor_final_guard_report": "phase8_4_signed_testnet_executor_final_guard_report.json",
    "phase9_3_status_polling_cancel_handling_report": "phase9_3_status_polling_cancel_handling_report.json",
}

APPLICATION_BOUNDARY_REQUIRED_FIELDS = [
    "source_runtime_authority_validator_id",
    "source_runtime_authority_validator_hash",
    "source_operator_filled_request_hash",
    "application_boundary_scope",
    "real_operator_approval_record_required",
    "real_operator_approval_record_present",
    "fresh_preorder_risk_gate_refresh_required_at_endpoint_time",
    "fresh_preorder_risk_gate_refresh_performed_at_endpoint_time",
    "secret_manager_runtime_binding_required",
    "secret_manager_runtime_binding_performed",
    "executor_policy_application_required",
    "executor_policy_application_performed",
    "endpoint_policy_application_required",
    "endpoint_policy_application_performed",
    "single_order_scope",
    "max_order_count",
    "small_max_notional_usd",
    "daily_loss_cap_usd",
    "idempotency_key_required",
    "idempotency_key_bound_to_real_order",
    "runtime_authority_application_performed",
    "runtime_authority_granted",
    "phase9_2_order_submission_authorized",
]

REMAINING_APPLICATION_BOUNDARY_BLOCKERS = [
    "PHASE9_2_APPLICATION_REQUIRES_REAL_OPERATOR_APPROVAL_RECORD_NOT_FIXTURE",
    "PHASE9_2_APPLICATION_REQUIRES_FRESH_PREORDER_RISK_GATE_AT_ENDPOINT_TIME",
    "PHASE9_2_APPLICATION_REQUIRES_SECRET_MANAGER_RUNTIME_BINDING_OUTSIDE_REVIEW_ARTIFACTS",
    "PHASE9_2_APPLICATION_REQUIRES_EXECUTOR_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_APPLICATION_REQUIRES_ENDPOINT_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_APPLICATION_DOES_NOT_CREATE_SIGNATURE_OR_HTTP_REQUEST",
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


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type") or data.get("gate_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_2_runtime_authority_change_request_validator_report":
        return (
            data.get("status") == STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED
            and data.get("phase9_2_runtime_authority_change_request_validator_recorded") is True
            and data.get("operator_filled_request_field_level_valid") is True
            and data.get("validator_grants_runtime_authority") is False
            and data.get("runtime_authority_granted") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_2_runtime_authority_operator_filled_fixture":
        return (
            data.get("artifact_type") == "phase9_2_operator_filled_runtime_authority_change_request_fixture_review_only"
            and data.get("review_only") is True
            and data.get("still_disabled") is True
            and data.get("runtime_authority_granted") is False
            and data.get("phase9_2_order_submission_authorized") is False
            and validate_operator_filled_runtime_authority_change_request(data).get("phase9_2_operator_filled_request_field_level_valid") is True
        )
    if name == "phase9_2_runtime_authority_operator_values_validation":
        return data.get("phase9_2_operator_filled_request_field_level_valid") is True and data.get("runtime_authority_granted") is False
    if name == "phase9_2_runtime_authority_change_request_report":
        return data.get("runtime_authority_granted") is False and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_runtime_authority_bridge_report":
        return data.get("runtime_authority_preconditions_ready_for_manual_design_review") is True and data.get("runtime_authority_granted") is False
    if name == "phase9_2_real_submit_gate_report":
        return data.get("phase9_2_real_submit_preconditions_ready_for_manual_runtime_review") is True and data.get("phase9_2_real_submit_authorized") is False
    if name == "phase8_3_hot_path_risk_gate_report":
        return data.get("phase8_3_hot_path_risk_gate_ready") is True and data.get("phase8_4_final_guard_may_begin") is True
    if name == "phase8_4_signed_testnet_executor_final_guard_report":
        return data.get("phase8_4_signed_testnet_executor_final_guard_ready") is True and data.get("signed_order_executor_enabled") is False
    if name == "phase9_3_status_polling_cancel_handling_report":
        return (data.get("phase9_3_status_polling_cancel_handling_design_recorded") is True or data.get("phase9_3_design_recorded") is True) and data.get("phase9_4_testnet_reconciliation_may_begin") is False
    return True


def _runtime_unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in FALSE_FLAGS if _safe_bool(data.get(field))]
    extra_false = [
        "runtime_authority_application_performed",
        "runtime_authority_application_approved",
        "runtime_authority_granted",
        "secret_manager_runtime_binding_performed",
        "runtime_key_value_loaded",
        "runtime_api_secret_loaded",
        "runtime_private_key_loaded",
        "executor_policy_application_performed",
        "endpoint_policy_application_performed",
        "signed_testnet_executor_enabled",
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "endpoint_policy_changed",
        "phase9_2_real_submit_authorized",
        "phase9_2_order_submission_authorized",
        "phase9_3_status_polling_may_begin",
        "phase9_4_testnet_reconciliation_may_begin",
        "real_order_id_created",
        "idempotency_key_bound_to_real_order",
        "order_endpoint_called",
        "order_status_endpoint_called",
        "cancel_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "actual_order_submission_performed",
    ]
    fields.extend([field for field in extra_false if _safe_bool(data.get(field))])
    fields.extend(unsafe_truthy_fields(data))
    return sorted(dict.fromkeys(fields))


def build_runtime_authority_application_boundary_template(
    validator_report: Mapping[str, Any], operator_fixture: Mapping[str, Any]
) -> dict[str, Any]:
    validator = dict(validator_report or {})
    fixture = dict(operator_fixture or {})
    source_validator_id = str(validator.get("phase9_2_runtime_authority_change_request_validator_id") or "missing_validator_id")
    source_validator_hash = str(validator.get("phase9_2_runtime_authority_change_request_validator_report_sha256") or sha256_json(validator))
    source_fixture_hash = sha256_json(fixture)
    boundary_seed = {
        "source_validator_id": source_validator_id,
        "source_validator_hash": source_validator_hash,
        "source_fixture_hash": source_fixture_hash,
    }
    boundary_id = stable_id("phase9_2_runtime_authority_application_boundary", boundary_seed, 24)
    template = {
        "artifact_type": "phase9_2_runtime_authority_application_boundary_template_still_disabled_review_only",
        "application_boundary_id": boundary_id,
        "application_boundary_version": PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_runtime_authority_validator_id": source_validator_id,
        "source_runtime_authority_validator_hash": source_validator_hash,
        "source_operator_filled_request_hash": source_fixture_hash,
        "source_operator_change_ticket_or_record_id": fixture.get("operator_change_ticket_or_record_id"),
        "source_metadata_only_testnet_key_fingerprint_sha256": fixture.get("metadata_only_testnet_key_fingerprint_sha256"),
        "application_boundary_scope": "single_signed_testnet_order_runtime_authority_application_design_only",
        "real_operator_approval_record_required": True,
        "real_operator_approval_record_present": False,
        "fresh_preorder_risk_gate_refresh_required_at_endpoint_time": True,
        "fresh_preorder_risk_gate_refresh_performed_at_endpoint_time": False,
        "secret_manager_runtime_binding_required": True,
        "secret_manager_runtime_binding_performed": False,
        "executor_policy_application_required": True,
        "executor_policy_application_performed": False,
        "endpoint_policy_application_required": True,
        "endpoint_policy_application_performed": False,
        "single_order_scope": True,
        "max_order_count": 1,
        "small_max_notional_usd": fixture.get("small_max_notional_usd", 10.0),
        "daily_loss_cap_usd": fixture.get("daily_loss_cap_usd", 15.0),
        "idempotency_key_required": True,
        "idempotency_key_bound_to_real_order": False,
        "runtime_authority_application_approved": False,
        "runtime_authority_application_performed": False,
        "runtime_authority_granted": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        **_flag_false_payload(),
        "secret_manager_runtime_binding_performed": False,
        "signed_testnet_executor_enabled": False,
        "endpoint_policy_changed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
    }
    template["runtime_authority_application_boundary_template_sha256"] = sha256_json(template)
    return template


def validate_runtime_authority_application_boundary_template(template: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(template or {})
    blockers: list[str] = []
    missing = [field for field in APPLICATION_BOUNDARY_REQUIRED_FIELDS if field not in data]
    blockers.extend(f"PHASE9_2_APPLICATION_BOUNDARY_MISSING_FIELD:{field}" for field in missing)
    unsafe = _runtime_unsafe_fields(data)
    secret_like_values = _find_secret_like_values(data)
    if data.get("artifact_type") != "phase9_2_runtime_authority_application_boundary_template_still_disabled_review_only":
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_NOT_REVIEW_ONLY_STILL_DISABLED")
    if not data.get("source_runtime_authority_validator_id"):
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_MISSING_SOURCE_VALIDATOR_ID")
    if not data.get("source_runtime_authority_validator_hash"):
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_MISSING_SOURCE_VALIDATOR_HASH")
    if not data.get("source_operator_filled_request_hash"):
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_MISSING_SOURCE_OPERATOR_REQUEST_HASH")
    if data.get("real_operator_approval_record_required") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_REAL_OPERATOR_APPROVAL_NOT_REQUIRED")
    if data.get("real_operator_approval_record_present") is not False:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_REAL_OPERATOR_APPROVAL_PRESENT_UNEXPECTED")
    if data.get("fresh_preorder_risk_gate_refresh_required_at_endpoint_time") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_FRESH_RISK_REFRESH_NOT_REQUIRED")
    if data.get("fresh_preorder_risk_gate_refresh_performed_at_endpoint_time") is not False:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_FRESH_RISK_REFRESH_PERFORMED_UNEXPECTED")
    if data.get("secret_manager_runtime_binding_required") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_SECRET_BINDING_NOT_REQUIRED")
    if data.get("secret_manager_runtime_binding_performed") is not False:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_SECRET_BINDING_PERFORMED_UNEXPECTED")
    if data.get("executor_policy_application_required") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_EXECUTOR_POLICY_APPLICATION_NOT_REQUIRED")
    if data.get("executor_policy_application_performed") is not False:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_EXECUTOR_POLICY_APPLICATION_PERFORMED_UNEXPECTED")
    if data.get("endpoint_policy_application_required") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_ENDPOINT_POLICY_APPLICATION_NOT_REQUIRED")
    if data.get("endpoint_policy_application_performed") is not False:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_ENDPOINT_POLICY_APPLICATION_PERFORMED_UNEXPECTED")
    if data.get("single_order_scope") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_SINGLE_ORDER_SCOPE_MISSING")
    try:
        max_order_count = int(data.get("max_order_count"))
    except (TypeError, ValueError):
        max_order_count = 0
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_MAX_ORDER_COUNT_INVALID")
    if max_order_count != 1:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_MAX_ORDER_COUNT_NOT_ONE")
    try:
        max_notional = float(data.get("small_max_notional_usd"))
    except (TypeError, ValueError):
        max_notional = 0.0
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_MAX_NOTIONAL_INVALID")
    if max_notional <= 0 or max_notional > 10.0:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_MAX_NOTIONAL_EXCEEDS_SMALL_CAP")
    try:
        daily_loss_cap = float(data.get("daily_loss_cap_usd"))
    except (TypeError, ValueError):
        daily_loss_cap = 0.0
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_DAILY_LOSS_CAP_INVALID")
    if daily_loss_cap <= 0 or daily_loss_cap > 15.0:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_DAILY_LOSS_CAP_EXCEEDS_LIMIT")
    if data.get("idempotency_key_required") is not True:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_IDEMPOTENCY_KEY_NOT_REQUIRED")
    if data.get("idempotency_key_bound_to_real_order") is not False:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_IDEMPOTENCY_BOUND_TO_REAL_ORDER_UNEXPECTED")
    if unsafe:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_UNSAFE_FLAGS:" + ",".join(unsafe))
    if secret_like_values:
        blockers.append("PHASE9_2_APPLICATION_BOUNDARY_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like_values))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_runtime_authority_application_boundary_validation_report",
        "phase9_2_runtime_authority_application_boundary_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like_values,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "runtime_authority_application_approved": False,
        "runtime_authority_application_performed": False,
        "runtime_authority_granted": False,
        "phase9_2_order_submission_authorized": False,
        **_flag_false_payload(),
    }


def _build_negative_fixture_results(valid_template: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "missing_source_validator_hash": {"source_runtime_authority_validator_hash": ""},
        "real_operator_approval_present_true": {"real_operator_approval_record_present": True},
        "fresh_risk_refresh_performed_true": {"fresh_preorder_risk_gate_refresh_performed_at_endpoint_time": True},
        "secret_binding_performed_true": {"secret_manager_runtime_binding_performed": True},
        "executor_policy_application_performed_true": {"executor_policy_application_performed": True},
        "endpoint_policy_application_performed_true": {"endpoint_policy_application_performed": True},
        "runtime_authority_application_performed_true": {"runtime_authority_application_performed": True},
        "runtime_authority_granted_true": {"runtime_authority_granted": True},
        "signed_testnet_executor_enabled_true": {"signed_testnet_executor_enabled": True},
        "endpoint_policy_changed_true": {"endpoint_policy_changed": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "idempotency_bound_to_real_order_true": {"idempotency_key_bound_to_real_order": True},
        "max_order_count_gt_one": {"max_order_count": 2},
        "max_notional_too_large": {"small_max_notional_usd": 1000.0},
        "daily_loss_cap_too_large": {"daily_loss_cap_usd": 500.0},
        "raw_secret_value_present": {"api_secret": "raw-secret-value-should-block"},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "signature_created_true": {"signature_created": True},
        "http_request_sent_true": {"http_request_sent": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(valid_template)
        payload.update(patch)
        validation = validate_runtime_authority_application_boundary_template(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_runtime_authority_application_boundary_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def build_phase9_2_runtime_authority_application_boundary_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_validator_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_validator_first:
        persist_phase9_2_runtime_authority_change_request_validator_report(cfg=cfg, run_change_request_first=True)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    evidence_ready = not missing and not not_ready and not unsafe

    validator_report = sources.get("phase9_2_runtime_authority_change_request_validator_report", {})
    operator_fixture = sources.get("phase9_2_runtime_authority_operator_filled_fixture", {})
    template = build_runtime_authority_application_boundary_template(validator_report, operator_fixture)
    validation = validate_runtime_authority_application_boundary_template(template)
    negative_fixture_results = _build_negative_fixture_results(template)

    boundary_id = template.get("application_boundary_id") or stable_id("phase9_2_runtime_authority_application_boundary", {"created_at_utc": created}, 24)
    recorded = evidence_ready and validation["phase9_2_runtime_authority_application_boundary_valid"] is True and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    status = STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED if recorded else STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_BLOCKED_REVIEW_ONLY
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_APPLICATION_BOUNDARY_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_APPLICATION_BOUNDARY_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_APPLICATION_BOUNDARY_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers.extend(REMAINING_APPLICATION_BOUNDARY_BLOCKERS)
    report = {
        "phase9_2_runtime_authority_application_boundary_id": boundary_id,
        "phase9_2_runtime_authority_application_boundary_version": PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_runtime_authority_application_boundary_recorded": recorded,
        "runtime_authority_application_boundary_template_valid": validation["phase9_2_runtime_authority_application_boundary_valid"],
        "runtime_authority_application_boundary_complete": False,
        "runtime_authority_application_approved": False,
        "runtime_authority_application_performed": False,
        "runtime_authority_granted": False,
        "secret_manager_runtime_binding_performed": False,
        "executor_policy_application_performed": False,
        "endpoint_policy_application_performed": False,
        "signed_testnet_executor_enabled": False,
        "endpoint_policy_changed": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "source_runtime_authority_validator_id": template.get("source_runtime_authority_validator_id"),
        "source_runtime_authority_validator_hash": template.get("source_runtime_authority_validator_hash"),
        "source_operator_filled_request_hash": template.get("source_operator_filled_request_hash"),
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "application_boundary_validation_report": validation,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers + validation.get("block_reasons", []))),
        "recommended_next_action": "keep_runtime_authority_application_boundary_still_disabled_until_real_manual_application_and_fresh_endpoint_time_risk_refresh_are_available",
        **_flag_false_payload(),
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_2_runtime_authority_application_boundary_report_sha256"] = sha256_json(report)
    return report, template, validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Runtime Authority Application Boundary - Still Disabled",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This boundary defines the separate application step that would be required after a validated runtime authority change request. It does not apply runtime authority, bind secrets, enable executors, change endpoint policy, create signatures, send HTTP requests, or submit orders.",
            "",
            "## Result",
            "",
            f"- Application boundary recorded: `{report.get('phase9_2_runtime_authority_application_boundary_recorded')}`",
            f"- Template valid: `{report.get('runtime_authority_application_boundary_template_valid')}`",
            f"- Runtime authority application performed: `{report.get('runtime_authority_application_performed')}`",
            f"- Runtime authority granted: `{report.get('runtime_authority_granted')}`",
            f"- Phase 9.2 order submission authorized: `{report.get('phase9_2_order_submission_authorized')}`",
            "",
            "## Still Disabled",
            "",
            "- `runtime_authority_application_performed=false`",
            "- `runtime_authority_granted=false`",
            "- `secret_manager_runtime_binding_performed=false`",
            "- `executor_policy_application_performed=false`",
            "- `endpoint_policy_application_performed=false`",
            "- `signed_order_executor_enabled=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "- `actual_order_submission_performed=false`",
            "",
        ]
    )


def persist_phase9_2_runtime_authority_application_boundary_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_validator_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_runtime_authority_application_boundary")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, validation, negative_fixture_results = build_phase9_2_runtime_authority_application_boundary_report(
        cfg=cfg,
        run_validator_first=run_validator_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_runtime_authority_application_boundary_report.json", report)
        atomic_write_json(base / "runtime_authority_application_boundary_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json", template)
        atomic_write_json(base / "phase9_2_runtime_authority_application_boundary_validation_report.json", validation)
        atomic_write_json(base / "phase9_2_runtime_authority_application_boundary_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_REGISTRY_NAME),
        {
            "phase9_2_runtime_authority_application_boundary_id": report.get("phase9_2_runtime_authority_application_boundary_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "runtime_authority_application_performed": False,
            "runtime_authority_granted": False,
            "phase9_2_order_submission_authorized": False,
            "secret_manager_runtime_binding_performed": False,
            "executor_policy_application_performed": False,
            "endpoint_policy_application_performed": False,
            "signed_testnet_executor_enabled": False,
            "endpoint_policy_changed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_REGISTRY_NAME,
        id_field="phase9_2_runtime_authority_application_boundary_registry_record_id",
        hash_field="phase9_2_runtime_authority_application_boundary_registry_record_sha256",
        id_prefix="phase9_2_runtime_authority_application_boundary_registry_record",
    )
    atomic_write_json(latest / "phase9_2_runtime_authority_application_boundary_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_runtime_authority_application_boundary_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_VERSION",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_BLOCKED_REVIEW_ONLY",
    "APPLICATION_BOUNDARY_REQUIRED_FIELDS",
    "REMAINING_APPLICATION_BOUNDARY_BLOCKERS",
    "build_runtime_authority_application_boundary_template",
    "validate_runtime_authority_application_boundary_template",
    "build_phase9_2_runtime_authority_application_boundary_report",
    "persist_phase9_2_runtime_authority_application_boundary_report",
]
