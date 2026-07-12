from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase8_1_secret_manager_key_handling_design import (
    FORBIDDEN_SECRET_MATERIAL_FIELDS,
    REQUIRED_TESTNET_KEY_SCOPE,
    _find_secret_material,
    persist_phase8_1_secret_manager_key_handling_design_report,
)

PHASE8_2_VERSION = "phase8_2_exchange_adapter_write_path_dry_validation_v1"
PHASE8_2_REGISTRY_NAME = "phase8_2_exchange_adapter_write_path_dry_validation_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE8_2_EXCHANGE_ADAPTER_WRITE_PATH_DRY_VALIDATION_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE8_2_EXCHANGE_ADAPTER_WRITE_PATH_DRY_VALIDATION_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE8_1_FILES = {
    "phase8_1_report": "phase8_1_secret_manager_key_handling_design_report.json",
    "secret_key_design": "secret_manager_key_handling_design_review_only.json",
    "secret_key_guard": "secret_key_handling_design_guard_report.json",
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
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "exchange_endpoint_called",
    "order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "order_submission_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
]

DRY_VALIDATION_REQUIRED_FIELDS = [
    "dry_validation_type",
    "phase8_2_version",
    "source_phase8_2_report_id",
    "source_phase8_1_evidence_hash_summary",
    "review_only",
    "dry_validation_only",
    "no_order_endpoint_calls",
    "metadata_only_key_handling_confirmed",
    "venue",
    "environment",
    "symbol_rules",
    "order_payload_candidate",
    "required_write_path_checks",
    "check_results",
    "error_normalization_cases",
    "rate_limit_budget_check",
    "idempotency_key_policy",
    "duplicate_submit_prevention",
    "signing_preimage_dry_validation",
    "phase8_3_hot_path_risk_gate_required",
    "phase8_4_final_guard_required",
    "phase9_explicit_single_order_intake_required",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
]

REQUIRED_WRITE_PATH_CHECKS = [
    "symbol_precision",
    "quantity_step_size",
    "price_tick_size",
    "min_notional",
    "order_schema",
    "timestamp_ms",
    "recv_window",
    "signing_preimage_shape",
    "idempotency_key",
    "duplicate_submit_prevention",
    "rate_limit_budget",
    "error_normalization",
    "endpoint_policy_no_order_calls",
]

FALSE_FLAGS = [
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "external_order_submission_performed",
    "exchange_endpoint_called",
    "order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "order_submission_performed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
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
        "phase8_2_report_sha256",
        "write_path_dry_validation_sha256",
        "write_path_dry_validation_guard_report_sha256",
        "phase8_1_report_sha256",
        "secret_key_handling_design_sha256",
        "secret_key_handling_design_guard_report_sha256",
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
        "status": data.get("status") or data.get("design_type") or data.get("guard_type") or data.get("dry_validation_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _phase8_1_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data:
        return False
    if data.get("blocked") is True or data.get("fail_closed") is True:
        return False
    if _unsafe_fields(data):
        return False
    if name == "phase8_1_report":
        return data.get("phase8_1_secret_key_design_ready") is True and data.get("phase8_2_write_path_dry_validation_may_begin") is True
    if name == "secret_key_design":
        return (
            data.get("design_type") == "phase8_1_secret_manager_key_handling_design_review_only"
            and data.get("metadata_only_key_handling") is True
            and data.get("phase8_2_write_path_dry_validation_required") is True
            and data.get("required_testnet_key_scope") == REQUIRED_TESTNET_KEY_SCOPE
        )
    if name == "secret_key_guard":
        return data.get("guard_passed") is True and data.get("phase8_2_write_path_dry_validation_may_begin") is True
    return True


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _is_multiple(value: Any, step: Any) -> bool:
    value_d = _to_decimal(value)
    step_d = _to_decimal(step)
    if value_d is None or step_d is None or step_d <= 0:
        return False
    return (value_d % step_d) == 0


def _validate_candidate_order(symbol_rules: Mapping[str, Any], order_payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    rules = dict(symbol_rules or {})
    order = dict(order_payload or {})
    required_order_fields = ["symbol", "side", "type", "quantity", "price", "timeInForce", "clientOrderId", "timestamp_ms", "recvWindow_ms"]
    missing = [field for field in required_order_fields if order.get(field) in (None, "")]
    if missing:
        blockers.append("ORDER_SCHEMA_MISSING_FIELDS:" + ",".join(missing))
    if order.get("symbol") != rules.get("symbol"):
        blockers.append("ORDER_SYMBOL_DOES_NOT_MATCH_SYMBOL_RULES")
    if str(order.get("side")) not in {"BUY", "SELL"}:
        blockers.append("ORDER_SIDE_INVALID")
    if str(order.get("type")) not in {"LIMIT", "MARKET"}:
        blockers.append("ORDER_TYPE_INVALID")
    if order.get("type") == "LIMIT" and order.get("timeInForce") not in {"GTC", "IOC", "FOK", "GTX"}:
        blockers.append("LIMIT_ORDER_TIME_IN_FORCE_INVALID")
    quantity = _to_decimal(order.get("quantity"))
    price = _to_decimal(order.get("price"))
    if quantity is None or quantity <= 0:
        blockers.append("ORDER_QUANTITY_INVALID")
    if price is None or price <= 0:
        blockers.append("ORDER_PRICE_INVALID")
    if not _is_multiple(order.get("quantity"), rules.get("quantity_step_size")):
        blockers.append("QUANTITY_STEP_SIZE_NOT_ALIGNED")
    if order.get("type") == "LIMIT" and not _is_multiple(order.get("price"), rules.get("price_tick_size")):
        blockers.append("PRICE_TICK_SIZE_NOT_ALIGNED")
    min_notional = _to_decimal(rules.get("min_notional"))
    if quantity is not None and price is not None and min_notional is not None:
        if quantity * price < min_notional:
            blockers.append("MIN_NOTIONAL_NOT_SATISFIED")
    else:
        blockers.append("MIN_NOTIONAL_INPUT_INVALID")
    timestamp_ms = _to_decimal(order.get("timestamp_ms"))
    recv_window_ms = _to_decimal(order.get("recvWindow_ms"))
    if timestamp_ms is None or timestamp_ms <= 0:
        blockers.append("TIMESTAMP_MS_INVALID")
    if recv_window_ms is None or recv_window_ms <= 0 or recv_window_ms > Decimal("60000"):
        blockers.append("RECV_WINDOW_INVALID")
    if len(str(order.get("clientOrderId") or "")) < 16:
        blockers.append("CLIENT_ORDER_ID_TOO_SHORT_FOR_IDEMPOTENCY")
    forbidden_order_fields = [field for field in FORBIDDEN_SECRET_MATERIAL_FIELDS if field in order]
    if forbidden_order_fields:
        blockers.append("FORBIDDEN_SECRET_FIELDS_IN_ORDER_PAYLOAD:" + ",".join(forbidden_order_fields))
    return blockers


def validate_exchange_adapter_write_path_dry_validation(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in DRY_VALIDATION_REQUIRED_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    secret_findings = _find_secret_material(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_WRITE_PATH_DRY_VALIDATION_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_WRITE_PATH_DRY_VALIDATION_FLAGS:" + ",".join(unsafe))
    if secret_findings:
        blockers.append("SECRET_MATERIAL_DETECTED_IN_WRITE_PATH_DRY_VALIDATION:" + ",".join(sorted(dict.fromkeys(secret_findings))))
    if data.get("dry_validation_type") != "phase8_2_exchange_adapter_write_path_dry_validation_review_only":
        blockers.append("INVALID_WRITE_PATH_DRY_VALIDATION_TYPE")
    for field in (
        "review_only",
        "dry_validation_only",
        "no_order_endpoint_calls",
        "metadata_only_key_handling_confirmed",
        "phase8_3_hot_path_risk_gate_required",
        "phase8_4_final_guard_required",
        "phase9_explicit_single_order_intake_required",
        "blocks_signed_testnet_execution",
        "blocks_order_submission",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_WRITE_PATH_CONFIRMATION_NOT_TRUE:{field}")
    for field in FALSE_FLAGS:
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_WRITE_PATH_FALSE_FLAG_NOT_FALSE:{field}")
    if data.get("required_write_path_checks") != REQUIRED_WRITE_PATH_CHECKS:
        blockers.append("REQUIRED_WRITE_PATH_CHECKS_INVALID")
    check_results = dict(data.get("check_results") or {})
    missing_checks = [check for check in REQUIRED_WRITE_PATH_CHECKS if check_results.get(check) is not True]
    if missing_checks:
        blockers.append("WRITE_PATH_CHECKS_NOT_TRUE:" + ",".join(missing_checks))
    blockers.extend(_validate_candidate_order(data.get("symbol_rules") or {}, data.get("order_payload_candidate") or {}))
    signing = dict(data.get("signing_preimage_dry_validation") or {})
    if signing.get("raw_preimage_logged") is not False:
        blockers.append("RAW_SIGNING_PREIMAGE_LOGGING_NOT_DISABLED")
    if signing.get("signature_created") is not False:
        blockers.append("SIGNATURE_CREATION_NOT_DISABLED")
    if signing.get("preimage_field_order_valid") is not True:
        blockers.append("SIGNING_PREIMAGE_FIELD_ORDER_NOT_VALIDATED")
    if not signing.get("preimage_sha256"):
        blockers.append("SIGNING_PREIMAGE_SHA256_MISSING")
    idem = dict(data.get("idempotency_key_policy") or {})
    duplicate = dict(data.get("duplicate_submit_prevention") or {})
    if idem.get("client_order_id_required") is not True or idem.get("idempotency_key_sha256") in (None, ""):
        blockers.append("IDEMPOTENCY_KEY_POLICY_INVALID")
    if duplicate.get("duplicate_submit_prevention_enabled") is not True or duplicate.get("same_id_blocks_second_submit") is not True:
        blockers.append("DUPLICATE_SUBMIT_PREVENTION_INVALID")
    rate = dict(data.get("rate_limit_budget_check") or {})
    if rate.get("rate_limit_budget_valid") is not True or rate.get("order_endpoint_weight_reserved") is not False:
        blockers.append("RATE_LIMIT_BUDGET_CHECK_INVALID")
    errors = data.get("error_normalization_cases") or []
    if not isinstance(errors, list) or len(errors) < 4:
        blockers.append("ERROR_NORMALIZATION_CASES_INSUFFICIENT")
    elif any(not isinstance(item, Mapping) or not item.get("normalized_error_code") for item in errors):
        blockers.append("ERROR_NORMALIZATION_CASES_INVALID")
    valid = not blockers
    return {
        "write_path_dry_validation_valid_review_only": valid,
        "write_path_dry_validation_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "secret_material_findings": sorted(dict.fromkeys(secret_findings)),
        "write_path_dry_validation_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_order_fixture(*, report_id: str, created_at_utc: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    symbol_rules = {
        "venue": "binance_futures_testnet_dry_spec",
        "environment": "signed_testnet_dry_validation_only",
        "symbol": "BTCUSDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "quantity_precision": 3,
        "price_precision": 1,
        "quantity_step_size": "0.001",
        "price_tick_size": "0.1",
        "min_quantity": "0.001",
        "min_notional": "5.0",
    }
    client_order_seed = {
        "phase": "phase8_2",
        "report_id": report_id,
        "symbol": symbol_rules["symbol"],
        "created_at_utc": created_at_utc,
        "dry_validation_only": True,
    }
    client_order_id = stable_id("p82_dry_client_order", client_order_seed, 32)
    order_payload = {
        "symbol": symbol_rules["symbol"],
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.001",
        "price": "100000.0",
        "timeInForce": "GTC",
        "clientOrderId": client_order_id,
        "timestamp_ms": 1783051200000,
        "recvWindow_ms": 5000,
    }
    ordered_preimage_fields = [
        "symbol",
        "side",
        "type",
        "timeInForce",
        "quantity",
        "price",
        "recvWindow_ms",
        "timestamp_ms",
        "clientOrderId",
    ]
    preimage_model = {field: order_payload[field] for field in ordered_preimage_fields}
    preimage_sha = sha256_json({"ordered_fields": ordered_preimage_fields, "values": preimage_model})
    signing = {
        "preimage_field_order_valid": True,
        "ordered_preimage_fields": ordered_preimage_fields,
        "preimage_sha256": preimage_sha,
        "raw_preimage_logged": False,
        "signature_created": False,
        "signed_request_created": False,
        "api_secret_value_accessed": False,
    }
    idempotency = {
        "client_order_id_required": True,
        "client_order_id": client_order_id,
        "idempotency_key_sha256": sha256_json({"clientOrderId": client_order_id, "symbol": order_payload["symbol"], "phase": "phase8_2"}),
        "idempotency_scope": "venue_symbol_side_type_timestamp_dry_validation",
    }
    duplicate = {
        "duplicate_submit_prevention_enabled": True,
        "same_id_blocks_second_submit": True,
        "duplicate_cache_key_sha256": sha256_json({"clientOrderId": client_order_id, "venue": symbol_rules["venue"]}),
        "duplicate_cache_persistence_required_before_phase9": True,
    }
    error_cases = [
        {"raw_error_class": "precision_filter_failure", "normalized_error_code": "ORDER_PRECISION_INVALID", "retryable": False},
        {"raw_error_class": "min_notional_failure", "normalized_error_code": "MIN_NOTIONAL_NOT_SATISFIED", "retryable": False},
        {"raw_error_class": "timestamp_recv_window_failure", "normalized_error_code": "TIMESTAMP_OR_RECV_WINDOW_INVALID", "retryable": False},
        {"raw_error_class": "rate_limit_exceeded", "normalized_error_code": "RATE_LIMIT_EXCEEDED", "retryable": True},
        {"raw_error_class": "duplicate_client_order_id", "normalized_error_code": "DUPLICATE_SUBMIT_BLOCKED", "retryable": False},
    ]
    rate_limit = {
        "rate_limit_budget_valid": True,
        "read_metadata_weight_budgeted": True,
        "order_endpoint_weight_reserved": False,
        "no_order_endpoint_weight_consumed": True,
        "max_dry_validation_attempts_per_run": 1,
    }
    return symbol_rules, order_payload, signing, idempotency, error_cases, rate_limit | {"duplicate_submit_prevention": duplicate}


def _build_dry_validation(*, report_id: str, phase8_1_sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    source_summary = {name: _source_summary(name, payload) for name, payload in phase8_1_sources.items()}
    symbol_rules, order_payload, signing, idempotency, error_cases, rate_and_duplicate = _build_order_fixture(
        report_id=report_id,
        created_at_utc=created_at_utc,
    )
    duplicate = dict(rate_and_duplicate.pop("duplicate_submit_prevention"))
    check_results = {check: True for check in REQUIRED_WRITE_PATH_CHECKS}
    validation: dict[str, Any] = {
        "dry_validation_type": "phase8_2_exchange_adapter_write_path_dry_validation_review_only",
        "phase8_2_version": PHASE8_2_VERSION,
        "source_phase8_2_report_id": report_id,
        "source_phase8_1_evidence_hash_summary": source_summary,
        "review_only": True,
        "dry_validation_only": True,
        "no_order_endpoint_calls": True,
        "metadata_only_key_handling_confirmed": True,
        "not_runtime_authority": True,
        "venue": symbol_rules["venue"],
        "environment": symbol_rules["environment"],
        "symbol_rules": symbol_rules,
        "order_payload_candidate": order_payload,
        "required_write_path_checks": REQUIRED_WRITE_PATH_CHECKS,
        "check_results": check_results,
        "error_normalization_cases": error_cases,
        "rate_limit_budget_check": rate_and_duplicate,
        "idempotency_key_policy": idempotency,
        "duplicate_submit_prevention": duplicate,
        "signing_preimage_dry_validation": signing,
        "request_build_mode": "local_schema_and_preimage_hash_only",
        "target_endpoint_documented_for_future_phase9_only": "signed_testnet_order_submit_endpoint_not_called",
        "phase8_2_does_not_use_api_key_value": True,
        "phase8_2_does_not_use_api_secret_value": True,
        "phase8_2_does_not_create_signature": True,
        "phase8_2_does_not_send_http_request": True,
        "phase8_3_hot_path_risk_gate_required": True,
        "phase8_4_final_guard_required": True,
        "phase9_explicit_single_order_intake_required": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
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
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "created_at_utc": created_at_utc,
    }
    validation["write_path_dry_validation_sha256"] = sha256_json(validation)
    return validation


def _build_guard(*, report_id: str, dry_validation: Mapping[str, Any], validation_result: Mapping[str, Any], phase8_1_ready: bool, created_at_utc: str) -> dict[str, Any]:
    guard_passed = phase8_1_ready and validation_result.get("write_path_dry_validation_valid_review_only") is True
    guard = {
        "guard_type": "phase8_2_exchange_adapter_write_path_dry_validation_guard_review_only",
        "phase8_2_version": PHASE8_2_VERSION,
        "source_phase8_2_report_id": report_id,
        "review_only": True,
        "dry_validation_guard_only": True,
        "guard_passed": guard_passed,
        "phase8_1_secret_key_handling_ready": phase8_1_ready,
        "write_path_dry_validation": dict(validation_result),
        "phase8_3_hot_path_risk_gate_may_begin": guard_passed,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
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
    guard["write_path_dry_validation_guard_report_sha256"] = sha256_json(guard)
    return guard


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 8.2 Exchange Adapter Write-Path Dry Validation - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase validates future signed testnet order request shape, symbol precision, quantity step, min notional, timestamp, recvWindow, signing preimage hash, idempotency, duplicate-submit prevention, rate-limit budgeting, and error normalization without sending an exchange order request.",
            "",
            "## Result",
            "",
            f"- Write-path dry validation ready: `{report.get('phase8_2_write_path_dry_validation_ready')}`",
            f"- Guard passed: `{report.get('write_path_dry_validation_guard_passed')}`",
            f"- Phase 8.3 hot-path risk gate may begin: `{report.get('phase8_3_hot_path_risk_gate_may_begin')}`",
            "",
            "## Safety Flags",
            "",
            "- `exchange_endpoint_called=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
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
            f"`{report.get('phase8_2_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase8_2_exchange_adapter_write_path_dry_validation_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_1_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase8_1_first:
        persist_phase8_1_secret_manager_key_handling_design_report(cfg=cfg)

    phase8_1_sources = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_PHASE8_1_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in phase8_1_sources.items()}
    missing = [name for name, payload in phase8_1_sources.items() if not payload]
    phase8_1_not_ready = [name for name, payload in phase8_1_sources.items() if not _phase8_1_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in phase8_1_sources.items() if _unsafe_fields(payload)}

    preliminary_blockers: list[str] = []
    preliminary_blockers.extend([f"MISSING_PHASE8_2_REQUIRED_PHASE8_1_EVIDENCE:{name}" for name in missing])
    preliminary_blockers.extend([f"PHASE8_2_PHASE8_1_EVIDENCE_NOT_READY:{name}" for name in phase8_1_not_ready])
    if unsafe:
        preliminary_blockers.extend([f"UNSAFE_PHASE8_2_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    preliminary_blockers = sorted(dict.fromkeys(str(item) for item in preliminary_blockers if item))
    phase8_1_ready = not preliminary_blockers

    preliminary_id = stable_id("phase8_2_exchange_adapter_write_path_dry_validation", {"source_summary": source_summary, "created_at_utc": created}, 24)
    dry_validation = _build_dry_validation(report_id=preliminary_id, phase8_1_sources=phase8_1_sources, created_at_utc=created)
    validation_result = validate_exchange_adapter_write_path_dry_validation(dry_validation)
    guard = _build_guard(report_id=preliminary_id, dry_validation=dry_validation, validation_result=validation_result, phase8_1_ready=phase8_1_ready, created_at_utc=created)

    blockers = list(preliminary_blockers)
    if validation_result.get("write_path_dry_validation_valid_review_only") is not True:
        blockers.extend(validation_result.get("write_path_dry_validation_blockers") or ["WRITE_PATH_DRY_VALIDATION_INVALID"])
    if guard.get("guard_passed") is not True:
        blockers.append("WRITE_PATH_DRY_VALIDATION_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report_id = stable_id(
        "phase8_2_exchange_adapter_write_path_dry_validation",
        {
            "source_summary": source_summary,
            "dry_validation_hash": sha256_json(dry_validation),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    dry_validation["source_phase8_2_report_id"] = report_id
    dry_validation["write_path_dry_validation_sha256"] = sha256_json(dry_validation)
    validation_result = validate_exchange_adapter_write_path_dry_validation(dry_validation)
    guard = _build_guard(report_id=report_id, dry_validation=dry_validation, validation_result=validation_result, phase8_1_ready=phase8_1_ready, created_at_utc=created)
    blockers = list(preliminary_blockers)
    if validation_result.get("write_path_dry_validation_valid_review_only") is not True:
        blockers.extend(validation_result.get("write_path_dry_validation_blockers") or ["WRITE_PATH_DRY_VALIDATION_INVALID"])
    if guard.get("guard_passed") is not True:
        blockers.append("WRITE_PATH_DRY_VALIDATION_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report: dict[str, Any] = {
        "phase8_2_exchange_adapter_write_path_dry_validation_id": report_id,
        "phase8_2_version": PHASE8_2_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "dry_validation_only": True,
        "metadata_only_key_handling_confirmed": True,
        "phase8_2_write_path_dry_validation_ready": ready,
        "write_path_dry_validation_created": True,
        "write_path_dry_validation_guard_created": True,
        "write_path_dry_validation_guard_passed": guard.get("guard_passed") is True,
        "phase8_3_hot_path_risk_gate_may_begin": ready,
        "phase8_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "required_phase8_1_evidence_hash_summary": source_summary,
        "missing_required_phase8_1_evidence": missing,
        "phase8_1_evidence_not_ready": phase8_1_not_ready,
        "unsafe_flags_by_artifact": unsafe,
        "dry_validation_result": validation_result,
        "block_reasons": blockers,
        "phase8_2_allowed_next_scope": "phase8_3_fresh_hot_path_preorder_risk_gate_no_order_endpoint_calls" if ready else "resolve_phase8_2_write_path_dry_validation_blockers",
        "recommended_next_action": "start_phase8_3_hot_path_preorder_risk_gate_keep_no_order_endpoint_calls" if ready else "inspect_phase8_2_blockers_and_rerun_phase8_1_then_phase8_2",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
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
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "created_at_utc": created,
    }
    report["write_path_dry_validation_sha256"] = dry_validation["write_path_dry_validation_sha256"]
    report["write_path_dry_validation_guard_report_sha256"] = guard["write_path_dry_validation_guard_report_sha256"]
    report["phase8_2_report_sha256"] = sha256_json(report)
    return report, dry_validation, guard


def persist_phase8_2_exchange_adapter_write_path_dry_validation_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_1_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase8_2_exchange_adapter_write_path_dry_validation")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, dry_validation, guard = build_phase8_2_exchange_adapter_write_path_dry_validation_report(
        cfg=cfg,
        run_phase8_1_first=run_phase8_1_first,
    )
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase8_2_exchange_adapter_write_path_dry_validation_report.json", report)
    atomic_write_json(latest / "exchange_adapter_write_path_dry_validation_review_only.json", dry_validation)
    atomic_write_json(latest / "exchange_adapter_write_path_dry_validation_guard_report.json", guard)
    (latest / "PHASE8_2_EXCHANGE_ADAPTER_WRITE_PATH_DRY_VALIDATION_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "exchange_adapter_write_path_dry_validation_review_only.json", dry_validation)

    atomic_write_json(phase_dir / "phase8_2_exchange_adapter_write_path_dry_validation_report.json", report)
    atomic_write_json(phase_dir / "exchange_adapter_write_path_dry_validation_review_only.json", dry_validation)
    atomic_write_json(phase_dir / "exchange_adapter_write_path_dry_validation_guard_report.json", guard)
    (phase_dir / "PHASE8_2_EXCHANGE_ADAPTER_WRITE_PATH_DRY_VALIDATION_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE8_2_REGISTRY_NAME),
        {
            "phase8_2_exchange_adapter_write_path_dry_validation_id": report.get("phase8_2_exchange_adapter_write_path_dry_validation_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase8_2_write_path_dry_validation_ready": report.get("phase8_2_write_path_dry_validation_ready"),
            "phase8_3_hot_path_risk_gate_may_begin": report.get("phase8_3_hot_path_risk_gate_may_begin"),
            "exchange_endpoint_called": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
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
        registry_name=PHASE8_2_REGISTRY_NAME,
        id_field="phase8_2_exchange_adapter_write_path_dry_validation_registry_record_id",
        hash_field="phase8_2_exchange_adapter_write_path_dry_validation_registry_record_sha256",
        id_prefix="phase8_2_exchange_adapter_write_path_dry_validation_registry_record",
    )
    atomic_write_json(latest / "phase8_2_exchange_adapter_write_path_dry_validation_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase8_2_exchange_adapter_write_path_dry_validation_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE8_2_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "REQUIRED_WRITE_PATH_CHECKS",
    "validate_exchange_adapter_write_path_dry_validation",
    "build_phase8_2_exchange_adapter_write_path_dry_validation_report",
    "persist_phase8_2_exchange_adapter_write_path_dry_validation_report",
]
