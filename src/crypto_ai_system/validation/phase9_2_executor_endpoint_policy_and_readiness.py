from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_secret_manager_runtime_binding_design import (
    persist_phase9_2_secret_manager_runtime_binding_report,
)
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import (
    _find_secret_like_values,
    _flag_false_payload,
    _safe_bool,
    _unsafe_fields,
)

PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_VERSION = "phase9_2_executor_endpoint_policy_readiness_v1"
PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_REGISTRY_NAME = "phase9_2_executor_endpoint_policy_readiness_registry"
STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_RECORDED_STILL_DISABLED = (
    "PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_RECORDED_STILL_DISABLED_REVIEW_ONLY"
)
STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_BLOCKED_REVIEW_ONLY = (
    "PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_BLOCKED_REVIEW_ONLY"
)

REQUIRED_SOURCE_FILES = {
    "secret_manager_runtime_binding_report": "phase9_2_secret_manager_runtime_binding_report.json",
    "endpoint_time_risk_refresh_report": "phase9_2_endpoint_time_risk_refresh_report.json",
    "runtime_authority_application_boundary_report": "phase9_2_runtime_authority_application_boundary_report.json",
    "real_submit_enablement_gate_report": "phase9_2_real_submit_enablement_gate_report.json",
    "blocked_executor_wrapper_report": "phase9_2_blocked_executor_wrapper_report.json",
    "status_polling_cancel_handling_report": "phase9_3_status_polling_cancel_handling_report.json",
}

EXECUTOR_POLICY_REQUIRED_FIELDS = [
    "executor_policy_application_design_id",
    "source_secret_manager_runtime_binding_hash",
    "source_endpoint_time_risk_refresh_hash",
    "executor_policy_application_required_before_real_submit",
    "executor_policy_application_performed",
    "signed_order_executor_enabled",
    "place_order_enabled",
    "cancel_order_enabled",
    "testnet_order_submission_allowed",
    "phase9_2_order_submission_authorized",
]

ENDPOINT_POLICY_REQUIRED_FIELDS = [
    "endpoint_policy_application_design_id",
    "source_executor_policy_application_design_hash",
    "order_endpoint_policy_application_required_before_real_submit",
    "endpoint_policy_application_performed",
    "endpoint_policy_changed",
    "order_endpoint_call_allowed",
    "order_status_endpoint_call_allowed",
    "cancel_endpoint_call_allowed",
    "http_request_allowed",
    "phase9_2_order_submission_authorized",
]

READINESS_REQUIRED_FIELDS = [
    "phase9_2_real_submit_readiness_packet_id",
    "source_executor_policy_application_design_hash",
    "source_endpoint_policy_application_design_hash",
    "source_secret_manager_runtime_binding_hash",
    "source_endpoint_time_risk_refresh_hash",
    "real_submit_readiness_packet_complete",
    "ready_for_separate_real_runtime_approval_review",
    "phase9_2_order_submission_authorized",
]

REMAINING_READINESS_BLOCKERS = [
    "PHASE9_2_READINESS_REQUIRES_SEPARATE_REAL_OPERATOR_APPROVAL_RECORD_NOT_FIXTURE",
    "PHASE9_2_READINESS_REQUIRES_ACTUAL_ENDPOINT_TIME_RISK_REFRESH_AT_SUBMIT_MOMENT",
    "PHASE9_2_READINESS_REQUIRES_SECRET_MANAGER_RUNTIME_BINDING_APPLICATION_NOT_PRESENT",
    "PHASE9_2_READINESS_REQUIRES_EXECUTOR_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_READINESS_REQUIRES_ENDPOINT_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_READINESS_DOES_NOT_CREATE_SIGNATURE_HTTP_OR_ORDER_ENDPOINT_CALL",
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


def _artifact_hash(payload: Mapping[str, Any]) -> str:
    return str(payload.get("sha256") or payload.get("report_sha256") or sha256_json(dict(payload or {})))


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "secret_manager_runtime_binding_report":
        return data.get("secret_manager_runtime_binding_design_ready") is True and data.get("secret_manager_runtime_binding_performed") is False
    if name == "endpoint_time_risk_refresh_report":
        return data.get("endpoint_time_risk_refresh_design_ready") is True and data.get("endpoint_time_risk_refresh_performed") is False
    if name == "runtime_authority_application_boundary_report":
        return data.get("runtime_authority_application_boundary_template_valid") is True and data.get("runtime_authority_application_performed") is False
    if name == "real_submit_enablement_gate_report":
        return data.get("phase9_2_real_submit_preconditions_ready_for_manual_runtime_review") is True and data.get("phase9_2_real_submit_authorized") is False
    if name == "blocked_executor_wrapper_report":
        return data.get("phase9_2_blocked_executor_wrapper_recorded") is True and data.get("actual_order_submission_performed") is False
    if name == "status_polling_cancel_handling_report":
        # Accept both older and newer field names.
        return (
            (data.get("phase9_3_status_polling_cancel_handling_design_recorded") is True or data.get("phase9_3_status_polling_cancel_handling_recorded") is True or data.get("phase9_3_design_recorded") is True)
            and data.get("order_status_endpoint_called") is False
            and data.get("cancel_endpoint_called") is False
        )
    return True


def _runtime_unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    false_fields = set(FALSE_FLAGS)
    false_fields.update({
        "executor_policy_application_performed",
        "endpoint_policy_application_performed",
        "endpoint_policy_changed",
        "secret_manager_runtime_binding_performed",
        "runtime_authority_granted",
        "runtime_authority_application_performed",
        "testnet_order_submission_allowed",
        "signed_order_executor_enabled",
        "place_order_enabled",
        "cancel_order_enabled",
        "phase9_2_order_submission_authorized",
        "phase9_2_real_submit_authorized",
        "order_endpoint_call_allowed",
        "order_status_endpoint_call_allowed",
        "cancel_endpoint_call_allowed",
        "http_request_allowed",
        "order_endpoint_called",
        "order_status_endpoint_called",
        "cancel_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "actual_order_submission_performed",
    })
    return sorted(field for field in false_fields if _safe_bool(data.get(field)))


def _base_disabled_payload() -> dict[str, Any]:
    return {
        **_flag_false_payload(),
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
    }


def build_executor_policy_application_design(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    secret_report = dict(sources.get("secret_manager_runtime_binding_report") or {})
    risk_report = dict(sources.get("endpoint_time_risk_refresh_report") or {})
    wrapper_report = dict(sources.get("blocked_executor_wrapper_report") or {})
    design_id = stable_id("phase9_2_executor_policy_application", {
        "secret": _artifact_hash(secret_report),
        "risk": _artifact_hash(risk_report),
        "wrapper": _artifact_hash(wrapper_report),
    }, 24)
    design = {
        "artifact_type": "phase9_2_executor_policy_application_design_still_disabled_review_only",
        "executor_policy_application_design_id": design_id,
        "version": PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_secret_manager_runtime_binding_hash": _artifact_hash(secret_report),
        "source_endpoint_time_risk_refresh_hash": _artifact_hash(risk_report),
        "source_blocked_executor_wrapper_hash": _artifact_hash(wrapper_report),
        "executor_policy_application_required_before_real_submit": True,
        "executor_policy_application_performed": False,
        "executor_policy_scope": "single_signed_testnet_order_only_max_order_count_1",
        "max_order_count": 1,
        "requires_real_operator_approval_record": True,
        "requires_endpoint_time_risk_refresh_execution": True,
        "requires_secret_manager_runtime_binding_application": True,
        "signed_order_executor_enabled": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "testnet_order_submission_allowed": False,
        "phase9_2_order_submission_authorized": False,
        **_base_disabled_payload(),
    }
    design["executor_policy_application_design_sha256"] = sha256_json(design)
    return design


def validate_executor_policy_application_design(design: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(design or {})
    blockers: list[str] = []
    blockers.extend(f"PHASE9_2_EXECUTOR_POLICY_MISSING_FIELD:{field}" for field in EXECUTOR_POLICY_REQUIRED_FIELDS if field not in data)
    if data.get("artifact_type") != "phase9_2_executor_policy_application_design_still_disabled_review_only":
        blockers.append("PHASE9_2_EXECUTOR_POLICY_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_EXECUTOR_POLICY_NOT_STILL_DISABLED_REVIEW_ONLY")
    if data.get("executor_policy_application_required_before_real_submit") is not True:
        blockers.append("PHASE9_2_EXECUTOR_POLICY_APPLICATION_NOT_REQUIRED")
    for field in ["executor_policy_application_performed", "signed_order_executor_enabled", "place_order_enabled", "cancel_order_enabled", "testnet_order_submission_allowed", "phase9_2_order_submission_authorized"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_EXECUTOR_POLICY_UNSAFE_FLAG:{field}")
    if data.get("max_order_count") != 1:
        blockers.append("PHASE9_2_EXECUTOR_POLICY_MAX_ORDER_COUNT_NOT_ONE")
    unsafe = _runtime_unsafe_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_EXECUTOR_POLICY_UNSAFE_FIELDS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_executor_policy_application_validation_report",
        "executor_policy_application_design_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_base_disabled_payload(),
    }


def build_endpoint_policy_application_design(executor_design: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    secret_report = dict(sources.get("secret_manager_runtime_binding_report") or {})
    risk_report = dict(sources.get("endpoint_time_risk_refresh_report") or {})
    status_design = dict(sources.get("status_polling_cancel_handling_report") or {})
    design_id = stable_id("phase9_2_endpoint_policy_application", {
        "executor": sha256_json(dict(executor_design or {})),
        "secret": _artifact_hash(secret_report),
        "risk": _artifact_hash(risk_report),
        "status": _artifact_hash(status_design),
    }, 24)
    design = {
        "artifact_type": "phase9_2_endpoint_policy_application_design_still_disabled_review_only",
        "endpoint_policy_application_design_id": design_id,
        "version": PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_executor_policy_application_design_hash": sha256_json(dict(executor_design or {})),
        "source_secret_manager_runtime_binding_hash": _artifact_hash(secret_report),
        "source_endpoint_time_risk_refresh_hash": _artifact_hash(risk_report),
        "source_status_polling_cancel_design_hash": _artifact_hash(status_design),
        "order_endpoint_policy_application_required_before_real_submit": True,
        "endpoint_policy_application_performed": False,
        "endpoint_policy_changed": False,
        "order_endpoint_call_allowed": False,
        "order_status_endpoint_call_allowed": False,
        "cancel_endpoint_call_allowed": False,
        "http_request_allowed": False,
        "endpoint_policy_scope": "single_signed_testnet_order_submit_only_status_cancel_separate_permissions",
        "duplicate_submit_prevention_required": True,
        "idempotency_key_required": True,
        "phase9_2_order_submission_authorized": False,
        **_base_disabled_payload(),
    }
    design["endpoint_policy_application_design_sha256"] = sha256_json(design)
    return design


def validate_endpoint_policy_application_design(design: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(design or {})
    blockers: list[str] = []
    blockers.extend(f"PHASE9_2_ENDPOINT_POLICY_MISSING_FIELD:{field}" for field in ENDPOINT_POLICY_REQUIRED_FIELDS if field not in data)
    if data.get("artifact_type") != "phase9_2_endpoint_policy_application_design_still_disabled_review_only":
        blockers.append("PHASE9_2_ENDPOINT_POLICY_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_ENDPOINT_POLICY_NOT_STILL_DISABLED_REVIEW_ONLY")
    if data.get("order_endpoint_policy_application_required_before_real_submit") is not True:
        blockers.append("PHASE9_2_ENDPOINT_POLICY_APPLICATION_NOT_REQUIRED")
    for field in ["endpoint_policy_application_performed", "endpoint_policy_changed", "order_endpoint_call_allowed", "order_status_endpoint_call_allowed", "cancel_endpoint_call_allowed", "http_request_allowed", "phase9_2_order_submission_authorized"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_ENDPOINT_POLICY_UNSAFE_FLAG:{field}")
    if data.get("duplicate_submit_prevention_required") is not True or data.get("idempotency_key_required") is not True:
        blockers.append("PHASE9_2_ENDPOINT_POLICY_IDEMPOTENCY_OR_DUPLICATE_GUARD_NOT_REQUIRED")
    unsafe = _runtime_unsafe_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_ENDPOINT_POLICY_UNSAFE_FIELDS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_endpoint_policy_application_validation_report",
        "endpoint_policy_application_design_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_base_disabled_payload(),
    }


def build_real_submit_readiness_packet(executor_design: Mapping[str, Any], endpoint_design: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    packet_id = stable_id("phase9_2_real_submit_readiness_packet", {
        "executor": sha256_json(dict(executor_design or {})),
        "endpoint": sha256_json(dict(endpoint_design or {})),
        "secret": _artifact_hash(sources.get("secret_manager_runtime_binding_report") or {}),
        "risk": _artifact_hash(sources.get("endpoint_time_risk_refresh_report") or {}),
    }, 24)
    packet = {
        "artifact_type": "phase9_2_real_submit_readiness_packet_still_disabled_review_only",
        "phase9_2_real_submit_readiness_packet_id": packet_id,
        "version": PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_executor_policy_application_design_hash": sha256_json(dict(executor_design or {})),
        "source_endpoint_policy_application_design_hash": sha256_json(dict(endpoint_design or {})),
        "source_secret_manager_runtime_binding_hash": _artifact_hash(sources.get("secret_manager_runtime_binding_report") or {}),
        "source_endpoint_time_risk_refresh_hash": _artifact_hash(sources.get("endpoint_time_risk_refresh_report") or {}),
        "real_submit_readiness_packet_complete": True,
        "ready_for_separate_real_runtime_approval_review": True,
        "real_submit_preconditions_documented": True,
        "requires_separate_real_operator_approval_record": True,
        "requires_actual_endpoint_time_risk_refresh_at_submit_moment": True,
        "requires_secret_manager_runtime_binding_application": True,
        "requires_executor_policy_application": True,
        "requires_endpoint_policy_application": True,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        **_base_disabled_payload(),
    }
    packet["phase9_2_real_submit_readiness_packet_sha256"] = sha256_json(packet)
    return packet


def validate_real_submit_readiness_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(packet or {})
    blockers: list[str] = []
    blockers.extend(f"PHASE9_2_READINESS_MISSING_FIELD:{field}" for field in READINESS_REQUIRED_FIELDS if field not in data)
    if data.get("artifact_type") != "phase9_2_real_submit_readiness_packet_still_disabled_review_only":
        blockers.append("PHASE9_2_READINESS_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_READINESS_NOT_STILL_DISABLED_REVIEW_ONLY")
    for field in ["phase9_2_real_submit_authorized", "phase9_2_order_submission_authorized", "testnet_order_submission_allowed", "signed_order_executor_enabled", "order_endpoint_called", "http_request_sent", "signature_created"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_READINESS_UNSAFE_FLAG:{field}")
    if data.get("real_submit_readiness_packet_complete") is not True:
        blockers.append("PHASE9_2_READINESS_PACKET_INCOMPLETE")
    if data.get("ready_for_separate_real_runtime_approval_review") is not True:
        blockers.append("PHASE9_2_READINESS_NOT_READY_FOR_MANUAL_REVIEW")
    unsafe = _runtime_unsafe_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_READINESS_UNSAFE_FIELDS:" + ",".join(unsafe))
    secret_like = [path for path in _find_secret_like_values(data) if "hash" not in path.lower() and "sha256" not in path.lower()]
    if secret_like:
        blockers.append("PHASE9_2_READINESS_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_real_submit_readiness_packet_validation_report",
        "real_submit_readiness_packet_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_base_disabled_payload(),
    }


def _negative_fixture_results(executor_design: Mapping[str, Any], endpoint_design: Mapping[str, Any], readiness_packet: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, tuple[str, Mapping[str, Any], Any]] = {
        "executor_policy_performed_true": ("executor", {"executor_policy_application_performed": True}, validate_executor_policy_application_design),
        "signed_executor_enabled_true": ("executor", {"signed_order_executor_enabled": True}, validate_executor_policy_application_design),
        "place_order_enabled_true": ("executor", {"place_order_enabled": True}, validate_executor_policy_application_design),
        "max_order_count_gt_one": ("executor", {"max_order_count": 2}, validate_executor_policy_application_design),
        "endpoint_policy_performed_true": ("endpoint", {"endpoint_policy_application_performed": True}, validate_endpoint_policy_application_design),
        "endpoint_policy_changed_true": ("endpoint", {"endpoint_policy_changed": True}, validate_endpoint_policy_application_design),
        "order_endpoint_call_allowed_true": ("endpoint", {"order_endpoint_call_allowed": True}, validate_endpoint_policy_application_design),
        "http_request_allowed_true": ("endpoint", {"http_request_allowed": True}, validate_endpoint_policy_application_design),
        "readiness_authorized_true": ("readiness", {"phase9_2_order_submission_authorized": True}, validate_real_submit_readiness_packet),
        "readiness_order_endpoint_called_true": ("readiness", {"order_endpoint_called": True}, validate_real_submit_readiness_packet),
        "readiness_signature_created_true": ("readiness", {"signature_created": True}, validate_real_submit_readiness_packet),
        "readiness_raw_secret_present": ("readiness", {"api_secret": "raw-secret-value-should-block"}, validate_real_submit_readiness_packet),
    }
    base = {"executor": dict(executor_design), "endpoint": dict(endpoint_design), "readiness": dict(readiness_packet)}
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
        "artifact_type": "phase9_2_executor_endpoint_policy_readiness_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked"] and item["fail_closed"] for item in results.values()),
        "fixture_results": results,
        **_base_disabled_payload(),
    }


def build_phase9_2_executor_endpoint_policy_readiness_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_secret_binding_first: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    if run_secret_binding_first:
        persist_phase9_2_secret_manager_runtime_binding_report(cfg=cfg, run_endpoint_time_refresh_first=True)
    created = utc_now_canonical()
    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe_sources = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    evidence_ready = not missing and not not_ready and not unsafe_sources

    executor_design = build_executor_policy_application_design(sources)
    executor_validation = validate_executor_policy_application_design(executor_design)
    endpoint_design = build_endpoint_policy_application_design(executor_design, sources)
    endpoint_validation = validate_endpoint_policy_application_design(endpoint_design)
    readiness_packet = build_real_submit_readiness_packet(executor_design, endpoint_design, sources)
    readiness_validation = validate_real_submit_readiness_packet(readiness_packet)
    negative_results = _negative_fixture_results(executor_design, endpoint_design, readiness_packet)

    recorded = (
        evidence_ready
        and executor_validation["executor_policy_application_design_valid"] is True
        and endpoint_validation["endpoint_policy_application_design_valid"] is True
        and readiness_validation["real_submit_readiness_packet_valid"] is True
        and negative_results["all_negative_fixtures_blocked_fail_closed"] is True
    )
    status = STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_RECORDED_STILL_DISABLED if recorded else STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_BLOCKED_REVIEW_ONLY
    report_id = stable_id("phase9_2_executor_endpoint_policy_readiness", {
        "executor": executor_design.get("executor_policy_application_design_sha256"),
        "endpoint": endpoint_design.get("endpoint_policy_application_design_sha256"),
        "readiness": readiness_packet.get("phase9_2_real_submit_readiness_packet_sha256"),
    }, 24)
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_POLICY_READINESS_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_POLICY_READINESS_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_POLICY_READINESS_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe_sources.items())
    blockers.extend(REMAINING_READINESS_BLOCKERS)
    blockers.extend(executor_validation.get("block_reasons", []))
    blockers.extend(endpoint_validation.get("block_reasons", []))
    blockers.extend(readiness_validation.get("block_reasons", []))
    report = {
        "phase9_2_executor_endpoint_policy_readiness_id": report_id,
        "phase9_2_executor_endpoint_policy_readiness_version": PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_executor_endpoint_policy_readiness_recorded": recorded,
        "executor_policy_application_design_ready": recorded,
        "endpoint_policy_application_design_ready": recorded,
        "real_submit_readiness_packet_ready_for_manual_review": recorded,
        "real_submit_readiness_packet_complete": recorded,
        "runtime_authority_granted": False,
        "runtime_authority_application_performed": False,
        "secret_manager_runtime_binding_performed": False,
        "executor_policy_application_performed": False,
        "endpoint_policy_application_performed": False,
        "endpoint_policy_changed": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe_sources,
        "executor_policy_application_validation_report": executor_validation,
        "endpoint_policy_application_validation_report": endpoint_validation,
        "real_submit_readiness_packet_validation_report": readiness_validation,
        "negative_fixture_results": negative_results,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "recommended_next_action": "keep_phase9_2_order_submission_disabled_until_separate_real_runtime_approval_secret_binding_risk_refresh_executor_policy_and_endpoint_policy_are_applied",
        **_base_disabled_payload(),
        "created_at_utc": created,
    }
    report["phase9_2_executor_endpoint_policy_readiness_report_sha256"] = sha256_json(report)
    return report, executor_design, endpoint_design, readiness_packet, executor_validation, endpoint_validation, readiness_validation, negative_results


def _handoff(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Phase 9.2 Executor/Endpoint Policy Application and Real Submit Readiness - Still Disabled",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This packet consolidates the still-disabled executor policy application design, endpoint policy application design, and real submit readiness packet for a single signed testnet order. It does not apply runtime authority, bind real secrets, enable executors, change endpoint policy, create signatures, send HTTP requests, call order endpoints, or authorize order submission.",
        "",
        "## Still Disabled Flags",
        "",
        "- `executor_policy_application_performed=false`",
        "- `endpoint_policy_application_performed=false`",
        "- `endpoint_policy_changed=false`",
        "- `signed_order_executor_enabled=false`",
        "- `order_endpoint_call_allowed=false`",
        "- `phase9_2_order_submission_authorized=false`",
        "- `actual_order_submission_performed=false`",
        "",
    ])


def persist_phase9_2_executor_endpoint_policy_readiness_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_secret_binding_first: bool = True) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_executor_endpoint_policy_readiness")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, executor_design, endpoint_design, readiness_packet, executor_validation, endpoint_validation, readiness_validation, negative_results = build_phase9_2_executor_endpoint_policy_readiness_report(
        cfg=cfg,
        run_secret_binding_first=run_secret_binding_first,
    )
    handoff = _handoff(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_executor_endpoint_policy_readiness_report.json", report)
        atomic_write_json(base / "executor_policy_application_DESIGN_STILL_DISABLED_REVIEW_ONLY.json", executor_design)
        atomic_write_json(base / "endpoint_policy_application_DESIGN_STILL_DISABLED_REVIEW_ONLY.json", endpoint_design)
        atomic_write_json(base / "real_submit_readiness_PACKET_STILL_DISABLED_REVIEW_ONLY.json", readiness_packet)
        atomic_write_json(base / "phase9_2_executor_policy_application_validation_report.json", executor_validation)
        atomic_write_json(base / "phase9_2_endpoint_policy_application_validation_report.json", endpoint_validation)
        atomic_write_json(base / "phase9_2_real_submit_readiness_packet_validation_report.json", readiness_validation)
        atomic_write_json(base / "phase9_2_executor_endpoint_policy_readiness_negative_fixture_results.json", negative_results)
        (base / "PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_REGISTRY_NAME),
        {
            "phase9_2_executor_endpoint_policy_readiness_id": report.get("phase9_2_executor_endpoint_policy_readiness_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "executor_policy_application_performed": False,
            "endpoint_policy_application_performed": False,
            "endpoint_policy_changed": False,
            "runtime_authority_granted": False,
            "phase9_2_order_submission_authorized": False,
            "signed_order_executor_enabled": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_REGISTRY_NAME,
        id_field="phase9_2_executor_endpoint_policy_readiness_registry_record_id",
        hash_field="phase9_2_executor_endpoint_policy_readiness_registry_record_sha256",
        id_prefix="phase9_2_executor_endpoint_policy_readiness_registry_record",
    )
    atomic_write_json(latest / "phase9_2_executor_endpoint_policy_readiness_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_executor_endpoint_policy_readiness_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_VERSION",
    "STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_RECORDED_STILL_DISABLED",
    "STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_BLOCKED_REVIEW_ONLY",
    "build_executor_policy_application_design",
    "validate_executor_policy_application_design",
    "build_endpoint_policy_application_design",
    "validate_endpoint_policy_application_design",
    "build_real_submit_readiness_packet",
    "validate_real_submit_readiness_packet",
    "build_phase9_2_executor_endpoint_policy_readiness_report",
    "persist_phase9_2_executor_endpoint_policy_readiness_report",
]
