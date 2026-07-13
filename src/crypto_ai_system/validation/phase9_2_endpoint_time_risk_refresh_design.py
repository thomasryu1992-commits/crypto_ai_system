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
from crypto_ai_system.validation.phase9_2_runtime_authority_application_boundary import (
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED,
    persist_phase9_2_runtime_authority_application_boundary_report,
)

PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_VERSION = "phase9_2_endpoint_time_risk_refresh_design_v1"
PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_REGISTRY_NAME = "phase9_2_endpoint_time_risk_refresh_registry"
STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED = (
    "PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED_REVIEW_ONLY"
)
STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_BLOCKED_REVIEW_ONLY = (
    "PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_BLOCKED_REVIEW_ONLY"
)

REQUIRED_SOURCE_FILES = {
    "phase9_2_runtime_authority_application_boundary_report": "phase9_2_runtime_authority_application_boundary_report.json",
    "phase8_3_hot_path_risk_gate_report": "phase8_3_hot_path_preorder_risk_gate_report.json",
    "phase8_4_signed_testnet_executor_final_guard_report": "phase8_4_signed_testnet_executor_final_guard_report.json",
    "phase9_2_real_submit_enablement_gate_report": "phase9_2_real_submit_enablement_gate_report.json",
    "phase9_2_runtime_authority_change_request_validator_report": "phase9_2_runtime_authority_change_request_validator_report.json",
    "phase9_3_status_polling_cancel_handling_report": "phase9_3_status_polling_cancel_handling_report.json",
}

REFRESH_REQUIRED_FIELDS = [
    "source_runtime_authority_application_boundary_id",
    "source_runtime_authority_application_boundary_hash",
    "source_hot_path_risk_gate_hash",
    "endpoint_time_refresh_scope",
    "fresh_market_data_required",
    "fresh_price_required",
    "price_freshness_window_seconds",
    "price_age_seconds",
    "price_freshness_status",
    "spread_bps",
    "max_spread_bps",
    "slippage_bps",
    "max_slippage_bps",
    "exposure_usd",
    "max_exposure_usd",
    "daily_loss_used_usd",
    "daily_loss_cap_usd",
    "consecutive_loss_count",
    "max_consecutive_loss",
    "hard_caps_passed",
    "kill_switch_confirmed_at_endpoint_time",
    "api_error_rate_rolling",
    "max_api_error_rate",
    "reconciliation_mismatch_open",
    "venue_readiness_passed",
    "canonical_id_chain_complete",
    "endpoint_time_risk_refresh_required",
    "endpoint_time_risk_refresh_performed",
    "runtime_authority_granted",
    "phase9_2_order_submission_authorized",
]

REMAINING_ENDPOINT_TIME_REFRESH_BLOCKERS = [
    "PHASE9_2_ENDPOINT_TIME_REFRESH_REQUIRES_REAL_MARKET_DATA_AT_ENDPOINT_TIME",
    "PHASE9_2_ENDPOINT_TIME_REFRESH_REQUIRES_REAL_OPERATOR_APPROVAL_RECORD_NOT_FIXTURE",
    "PHASE9_2_ENDPOINT_TIME_REFRESH_REQUIRES_SECRET_MANAGER_RUNTIME_BINDING_NOT_PERFORMED",
    "PHASE9_2_ENDPOINT_TIME_REFRESH_REQUIRES_EXECUTOR_POLICY_APPLICATION_NOT_PERFORMED",
    "PHASE9_2_ENDPOINT_TIME_REFRESH_REQUIRES_ENDPOINT_POLICY_APPLICATION_NOT_PERFORMED",
    "PHASE9_2_ENDPOINT_TIME_REFRESH_DOES_NOT_CREATE_SIGNATURE_OR_HTTP_REQUEST",
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
    if name == "phase9_2_runtime_authority_application_boundary_report":
        return (
            data.get("status") == STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED
            and data.get("phase9_2_runtime_authority_application_boundary_recorded") is True
            and data.get("runtime_authority_application_boundary_template_valid") is True
            and data.get("runtime_authority_application_performed") is False
            and data.get("runtime_authority_granted") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase8_3_hot_path_risk_gate_report":
        return data.get("phase8_3_hot_path_risk_gate_ready") is True and data.get("phase8_4_final_guard_may_begin") is True
    if name == "phase8_4_signed_testnet_executor_final_guard_report":
        return data.get("phase8_4_signed_testnet_executor_final_guard_ready") is True and data.get("signed_order_executor_enabled") is False
    if name == "phase9_2_real_submit_enablement_gate_report":
        return data.get("phase9_2_real_submit_preconditions_ready_for_manual_runtime_review") is True and data.get("phase9_2_real_submit_authorized") is False
    if name == "phase9_2_runtime_authority_change_request_validator_report":
        return data.get("operator_filled_request_field_level_valid") is True and data.get("runtime_authority_granted") is False
    if name == "phase9_3_status_polling_cancel_handling_report":
        return (data.get("phase9_3_status_polling_cancel_handling_design_recorded") is True or data.get("phase9_3_design_recorded") is True) and data.get("phase9_4_testnet_reconciliation_may_begin") is False
    return True


def _runtime_unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in FALSE_FLAGS if _safe_bool(data.get(field))]
    extra_false = [
        "endpoint_time_risk_refresh_performed",
        "endpoint_time_real_market_data_bound",
        "runtime_authority_granted",
        "runtime_authority_application_performed",
        "secret_manager_runtime_binding_performed",
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


def build_endpoint_time_risk_refresh_template(
    application_boundary_report: Mapping[str, Any], hot_path_risk_gate_report: Mapping[str, Any]
) -> dict[str, Any]:
    app = dict(application_boundary_report or {})
    risk = dict(hot_path_risk_gate_report or {})
    source_app_id = str(app.get("phase9_2_runtime_authority_application_boundary_id") or "missing_application_boundary_id")
    source_app_hash = str(app.get("phase9_2_runtime_authority_application_boundary_report_sha256") or sha256_json(app))
    source_risk_hash = str(risk.get("phase8_3_hot_path_preorder_risk_gate_report_sha256") or sha256_json(risk))
    refresh_id = stable_id(
        "phase9_2_endpoint_time_risk_refresh",
        {
            "source_application_boundary_id": source_app_id,
            "source_application_boundary_hash": source_app_hash,
            "source_hot_path_risk_gate_hash": source_risk_hash,
        },
        24,
    )
    template = {
        "artifact_type": "phase9_2_endpoint_time_risk_refresh_design_still_disabled_review_only",
        "endpoint_time_risk_refresh_id": refresh_id,
        "endpoint_time_risk_refresh_version": PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_runtime_authority_application_boundary_id": source_app_id,
        "source_runtime_authority_application_boundary_hash": source_app_hash,
        "source_hot_path_risk_gate_hash": source_risk_hash,
        "endpoint_time_refresh_scope": "single_signed_testnet_order_pre_submit_refresh_design_only",
        "fresh_market_data_required": True,
        "fresh_price_required": True,
        "price_freshness_window_seconds": 5,
        "price_age_seconds": 0,
        "price_freshness_status": "fresh_fixture_for_review_only",
        "stale_price_block_required": True,
        "spread_bps": 2.5,
        "max_spread_bps": 5.0,
        "slippage_bps": 3.0,
        "max_slippage_bps": 8.0,
        "exposure_usd": 0.0,
        "max_exposure_usd": 10.0,
        "daily_loss_used_usd": 0.0,
        "daily_loss_cap_usd": 15.0,
        "consecutive_loss_count": 0,
        "max_consecutive_loss": 2,
        "hard_caps_passed": True,
        "kill_switch_confirmed_at_endpoint_time": False,
        "kill_switch_confirmation_required_at_endpoint_time": True,
        "api_error_rate_rolling": 0.0,
        "max_api_error_rate": 0.02,
        "reconciliation_mismatch_open": False,
        "venue_readiness_passed": True,
        "canonical_id_chain_complete": True,
        "endpoint_time_risk_refresh_required": True,
        "endpoint_time_risk_refresh_performed": False,
        "endpoint_time_real_market_data_bound": False,
        "runtime_authority_granted": False,
        "runtime_authority_application_performed": False,
        "secret_manager_runtime_binding_performed": False,
        "executor_policy_application_performed": False,
        "endpoint_policy_application_performed": False,
        "signed_testnet_executor_enabled": False,
        "testnet_order_submission_allowed": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        **_flag_false_payload(),
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
    }
    template["endpoint_time_risk_refresh_template_sha256"] = sha256_json(template)
    return template


def validate_endpoint_time_risk_refresh_template(template: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(template or {})
    blockers: list[str] = []
    missing = [field for field in REFRESH_REQUIRED_FIELDS if field not in data]
    blockers.extend(f"PHASE9_2_ENDPOINT_TIME_REFRESH_MISSING_FIELD:{field}" for field in missing)
    unsafe = _runtime_unsafe_fields(data)
    secret_like_values = _find_secret_like_values(data)
    if data.get("artifact_type") != "phase9_2_endpoint_time_risk_refresh_design_still_disabled_review_only":
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_NOT_REVIEW_ONLY_STILL_DISABLED")
    if not data.get("source_runtime_authority_application_boundary_id"):
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_MISSING_SOURCE_APPLICATION_BOUNDARY_ID")
    if not data.get("source_runtime_authority_application_boundary_hash"):
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_MISSING_SOURCE_APPLICATION_BOUNDARY_HASH")
    if not data.get("source_hot_path_risk_gate_hash"):
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_MISSING_SOURCE_RISK_GATE_HASH")
    if data.get("fresh_market_data_required") is not True or data.get("fresh_price_required") is not True:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_FRESH_MARKET_DATA_NOT_REQUIRED")
    try:
        price_window = int(data.get("price_freshness_window_seconds"))
        price_age = int(data.get("price_age_seconds"))
    except (TypeError, ValueError):
        price_window = -1
        price_age = 999999
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_PRICE_FRESHNESS_INVALID")
    if price_window <= 0 or price_age < 0 or price_age > price_window:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_PRICE_STALE_OR_OUTSIDE_WINDOW")
    if str(data.get("price_freshness_status", "")).lower().startswith("stale"):
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_PRICE_STALE_STATUS")
    try:
        spread = float(data.get("spread_bps"))
        max_spread = float(data.get("max_spread_bps"))
        slippage = float(data.get("slippage_bps"))
        max_slippage = float(data.get("max_slippage_bps"))
    except (TypeError, ValueError):
        spread = slippage = 999999.0
        max_spread = max_slippage = 0.0
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_SPREAD_SLIPPAGE_INVALID")
    if max_spread <= 0 or spread > max_spread:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_SPREAD_EXCEEDS_LIMIT")
    if max_slippage <= 0 or slippage > max_slippage:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_SLIPPAGE_EXCEEDS_LIMIT")
    try:
        exposure = float(data.get("exposure_usd"))
        max_exposure = float(data.get("max_exposure_usd"))
        daily_loss = float(data.get("daily_loss_used_usd"))
        daily_loss_cap = float(data.get("daily_loss_cap_usd"))
    except (TypeError, ValueError):
        exposure = daily_loss = 999999.0
        max_exposure = daily_loss_cap = 0.0
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_EXPOSURE_OR_LOSS_INVALID")
    if max_exposure <= 0 or exposure > max_exposure:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_EXPOSURE_EXCEEDS_LIMIT")
    if daily_loss < 0 or daily_loss_cap <= 0 or daily_loss > daily_loss_cap:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_DAILY_LOSS_EXCEEDS_LIMIT")
    try:
        consecutive = int(data.get("consecutive_loss_count"))
        max_consecutive = int(data.get("max_consecutive_loss"))
    except (TypeError, ValueError):
        consecutive = 999999
        max_consecutive = 0
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_CONSECUTIVE_LOSS_INVALID")
    if max_consecutive < 0 or consecutive > max_consecutive:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_CONSECUTIVE_LOSS_EXCEEDS_LIMIT")
    if data.get("hard_caps_passed") is not True:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_HARD_CAPS_NOT_PASSED")
    if data.get("kill_switch_confirmation_required_at_endpoint_time") is not True:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_KILL_SWITCH_CONFIRMATION_NOT_REQUIRED")
    if data.get("kill_switch_confirmed_at_endpoint_time") is not False:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_KILL_SWITCH_CONFIRMED_UNEXPECTED_IN_REVIEW_ONLY")
    try:
        api_error_rate = float(data.get("api_error_rate_rolling"))
        max_api_error_rate = float(data.get("max_api_error_rate"))
    except (TypeError, ValueError):
        api_error_rate = 1.0
        max_api_error_rate = 0.0
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_API_ERROR_RATE_INVALID")
    if max_api_error_rate < 0 or api_error_rate > max_api_error_rate:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_API_ERROR_RATE_EXCEEDS_LIMIT")
    if data.get("reconciliation_mismatch_open") is not False:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_RECONCILIATION_MISMATCH_OPEN")
    if data.get("venue_readiness_passed") is not True:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_VENUE_READINESS_NOT_PASSED")
    if data.get("canonical_id_chain_complete") is not True:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_CANONICAL_ID_CHAIN_INCOMPLETE")
    if data.get("endpoint_time_risk_refresh_required") is not True:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_NOT_REQUIRED")
    if data.get("endpoint_time_risk_refresh_performed") is not False:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_PERFORMED_UNEXPECTED")
    if data.get("endpoint_time_real_market_data_bound") is not False:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_REAL_MARKET_DATA_BOUND_UNEXPECTED")
    if unsafe:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_UNSAFE_FLAGS:" + ",".join(unsafe))
    if secret_like_values:
        blockers.append("PHASE9_2_ENDPOINT_TIME_REFRESH_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like_values))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_endpoint_time_risk_refresh_validation_report",
        "phase9_2_endpoint_time_risk_refresh_template_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like_values,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "endpoint_time_risk_refresh_performed": False,
        "runtime_authority_granted": False,
        "phase9_2_order_submission_authorized": False,
        **_flag_false_payload(),
    }


def _build_negative_fixture_results(valid_template: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "missing_source_application_boundary_hash": {"source_runtime_authority_application_boundary_hash": ""},
        "stale_price_age_exceeds_window": {"price_age_seconds": 60, "price_freshness_window_seconds": 5},
        "stale_price_status": {"price_freshness_status": "stale"},
        "spread_exceeds_limit": {"spread_bps": 25.0},
        "slippage_exceeds_limit": {"slippage_bps": 50.0},
        "exposure_exceeds_limit": {"exposure_usd": 100.0},
        "daily_loss_exceeds_limit": {"daily_loss_used_usd": 50.0},
        "consecutive_loss_exceeds_limit": {"consecutive_loss_count": 5},
        "hard_caps_not_passed": {"hard_caps_passed": False},
        "kill_switch_confirmed_true_in_review_only": {"kill_switch_confirmed_at_endpoint_time": True},
        "api_error_rate_exceeds_limit": {"api_error_rate_rolling": 0.5},
        "reconciliation_mismatch_open": {"reconciliation_mismatch_open": True},
        "venue_readiness_not_passed": {"venue_readiness_passed": False},
        "canonical_id_chain_incomplete": {"canonical_id_chain_complete": False},
        "endpoint_refresh_performed_true": {"endpoint_time_risk_refresh_performed": True},
        "real_market_data_bound_true": {"endpoint_time_real_market_data_bound": True},
        "runtime_authority_granted_true": {"runtime_authority_granted": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "raw_secret_value_present": {"api_secret": "raw-secret-value-should-block"},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "signature_created_true": {"signature_created": True},
        "http_request_sent_true": {"http_request_sent": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(valid_template)
        payload.update(patch)
        validation = validate_endpoint_time_risk_refresh_template(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_endpoint_time_risk_refresh_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def build_phase9_2_endpoint_time_risk_refresh_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_application_boundary_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_application_boundary_first:
        persist_phase9_2_runtime_authority_application_boundary_report(cfg=cfg, run_validator_first=True)
    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    evidence_ready = not missing and not not_ready and not unsafe
    template = build_endpoint_time_risk_refresh_template(
        sources.get("phase9_2_runtime_authority_application_boundary_report", {}),
        sources.get("phase8_3_hot_path_risk_gate_report", {}),
    )
    validation = validate_endpoint_time_risk_refresh_template(template)
    negative_fixture_results = _build_negative_fixture_results(template)
    refresh_id = template.get("endpoint_time_risk_refresh_id") or stable_id("phase9_2_endpoint_time_risk_refresh", {"created_at_utc": created}, 24)
    recorded = evidence_ready and validation["phase9_2_endpoint_time_risk_refresh_template_valid"] is True and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    status = STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED if recorded else STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_BLOCKED_REVIEW_ONLY
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_ENDPOINT_TIME_REFRESH_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_ENDPOINT_TIME_REFRESH_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_ENDPOINT_TIME_REFRESH_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers.extend(REMAINING_ENDPOINT_TIME_REFRESH_BLOCKERS)
    report = {
        "phase9_2_endpoint_time_risk_refresh_id": refresh_id,
        "phase9_2_endpoint_time_risk_refresh_version": PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_endpoint_time_risk_refresh_recorded": recorded,
        "endpoint_time_risk_refresh_template_valid": validation["phase9_2_endpoint_time_risk_refresh_template_valid"],
        "endpoint_time_risk_refresh_design_ready": recorded,
        "endpoint_time_risk_refresh_performed": False,
        "endpoint_time_real_market_data_bound": False,
        "runtime_authority_granted": False,
        "runtime_authority_application_performed": False,
        "secret_manager_runtime_binding_performed": False,
        "executor_policy_application_performed": False,
        "endpoint_policy_application_performed": False,
        "signed_testnet_executor_enabled": False,
        "endpoint_policy_changed": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "source_runtime_authority_application_boundary_id": template.get("source_runtime_authority_application_boundary_id"),
        "source_runtime_authority_application_boundary_hash": template.get("source_runtime_authority_application_boundary_hash"),
        "source_hot_path_risk_gate_hash": template.get("source_hot_path_risk_gate_hash"),
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "endpoint_time_risk_refresh_validation_report": validation,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers + validation.get("block_reasons", []))),
        "recommended_next_action": "keep_endpoint_time_risk_refresh_design_still_disabled_until_real_endpoint_time_market_data_secret_binding_executor_policy_and_endpoint_policy_are_available",
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
    report["phase9_2_endpoint_time_risk_refresh_report_sha256"] = sha256_json(report)
    return report, template, validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Fresh Endpoint-Time Risk Refresh Design - Still Disabled",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact defines the fresh risk refresh that must run immediately before any future real signed testnet order endpoint call. It records the required checks but does not bind real market data, grant runtime authority, create signatures, send HTTP requests, or submit orders.",
            "",
            "## Required Endpoint-Time Checks",
            "",
            "- fresh price and staleness window",
            "- spread and slippage limits",
            "- exposure and daily loss limits",
            "- max consecutive loss",
            "- hard caps",
            "- kill switch confirmation at endpoint time",
            "- API error rate",
            "- reconciliation mismatch status",
            "- venue readiness",
            "- canonical ID chain completeness",
            "",
            "## Still Disabled",
            "",
            "- `endpoint_time_risk_refresh_performed=false`",
            "- `endpoint_time_real_market_data_bound=false`",
            "- `runtime_authority_granted=false`",
            "- `phase9_2_order_submission_authorized=false`",
            "- `signed_order_executor_enabled=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "- `actual_order_submission_performed=false`",
            "",
        ]
    )


def persist_phase9_2_endpoint_time_risk_refresh_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_application_boundary_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_endpoint_time_risk_refresh")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, validation, negative_fixture_results = build_phase9_2_endpoint_time_risk_refresh_report(
        cfg=cfg,
        run_application_boundary_first=run_application_boundary_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_endpoint_time_risk_refresh_report.json", report)
        atomic_write_json(base / "endpoint_time_risk_refresh_DESIGN_STILL_DISABLED_REVIEW_ONLY.json", template)
        atomic_write_json(base / "phase9_2_endpoint_time_risk_refresh_validation_report.json", validation)
        atomic_write_json(base / "phase9_2_endpoint_time_risk_refresh_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_REGISTRY_NAME),
        {
            "phase9_2_endpoint_time_risk_refresh_id": report.get("phase9_2_endpoint_time_risk_refresh_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "endpoint_time_risk_refresh_performed": False,
            "endpoint_time_real_market_data_bound": False,
            "runtime_authority_granted": False,
            "phase9_2_order_submission_authorized": False,
            "signed_testnet_executor_enabled": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_REGISTRY_NAME,
        id_field="phase9_2_endpoint_time_risk_refresh_registry_record_id",
        hash_field="phase9_2_endpoint_time_risk_refresh_registry_record_sha256",
        id_prefix="phase9_2_endpoint_time_risk_refresh_registry_record",
    )
    atomic_write_json(latest / "phase9_2_endpoint_time_risk_refresh_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_endpoint_time_risk_refresh_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_VERSION",
    "STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED",
    "STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_BLOCKED_REVIEW_ONLY",
    "REFRESH_REQUIRED_FIELDS",
    "REMAINING_ENDPOINT_TIME_REFRESH_BLOCKERS",
    "build_endpoint_time_risk_refresh_template",
    "validate_endpoint_time_risk_refresh_template",
    "build_phase9_2_endpoint_time_risk_refresh_report",
    "persist_phase9_2_endpoint_time_risk_refresh_report",
]
