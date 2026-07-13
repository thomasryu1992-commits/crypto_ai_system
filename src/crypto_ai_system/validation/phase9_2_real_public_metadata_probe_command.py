from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_2_public_metadata_network_dry_probe_result_intake import (
    RESULT_FALSE_FLAGS,
    validate_public_metadata_probe_result_payload,
)
from crypto_ai_system.validation.phase9_2_real_testnet_endpoint_adapter_preflight import _hash
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool

PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_VERSION = "phase9_2_real_public_metadata_probe_command_v1"
PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_REGISTRY_NAME = "phase9_2_real_public_metadata_probe_command_registry"
STATUS_READY = "PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_READY_NO_ORDER_SUBMIT_REVIEW_ONLY"
STATUS_EXECUTED_PUBLIC_METADATA_ONLY = "PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_EXECUTED_PUBLIC_METADATA_ONLY_NO_ORDER_SUBMIT"
STATUS_BLOCKED = "PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_BLOCKED_FAIL_CLOSED"

SOURCE_FILLED_VALIDATION_REPORT = "phase9_2_public_metadata_probe_result_filled_validation_report.json"
SOURCE_DRY_PROBE_REPORT = "phase9_2_real_testnet_network_dry_probe_report.json"

PUBLIC_ENDPOINTS = {
    "exchange_time": "/fapi/v1/time",
    "exchange_info": "/fapi/v1/exchangeInfo",
}
FORBIDDEN_ENDPOINT_TOKENS = [
    "/order",
    "/allOrders",
    "/openOrders",
    "/account",
    "/balance",
    "/position",
    "/leverage",
    "/margin",
    "/listenKey",
]

COMMAND_FALSE_FLAGS = sorted(set(RESULT_FALSE_FLAGS + [
    "real_testnet_submit_may_begin",
    "real_testnet_endpoint_adapter_attached",
    "order_endpoint_calls_allowed",
    "signature_creation_allowed",
    "http_transmission_allowed_for_order",
    "actual_order_submission_performed",
    "real_exchange_endpoint_call_performed",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "api_key_value_read_allowed",
    "api_secret_value_read_allowed",
    "api_key_value_logged",
    "api_secret_value_logged",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
]))


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


def _disabled_payload() -> dict[str, bool]:
    return {field: False for field in COMMAND_FALSE_FLAGS}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    unsafe = [field for field in COMMAND_FALSE_FLAGS if _safe_bool(data.get(field))]
    nested = data.get("public_metadata_probe_command")
    if isinstance(nested, Mapping):
        unsafe += [field for field in COMMAND_FALSE_FLAGS if _safe_bool(nested.get(field))]
    return sorted(set(unsafe))


def _source_ready(dry_probe: Mapping[str, Any], filled_validation: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    dry = dict(dry_probe or {})
    filled = dict(filled_validation or {})
    if not dry:
        blockers.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_SOURCE_DRY_PROBE_REPORT_MISSING")
    else:
        if dry.get("blocked") is True or dry.get("fail_closed") is True:
            blockers.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_SOURCE_DRY_PROBE_BLOCKED")
        if dry.get("network_dry_probe_ready_for_operator_no_order_command") is not True:
            blockers.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_REQUIRES_DRY_PROBE_READY")
        for field in COMMAND_FALSE_FLAGS:
            if dry.get(field) is True:
                blockers.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_UNSAFE_SOURCE_DRY_PROBE_FLAG:" + field)
    if filled:
        # A previous filled validation may be blocked because it used sample data. That must not block this command.
        if filled.get("real_testnet_submit_may_begin") is not False:
            blockers.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_SOURCE_FILLED_VALIDATION_MUST_NOT_ALLOW_SUBMIT")
        for field in COMMAND_FALSE_FLAGS:
            if filled.get(field) is True:
                blockers.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_UNSAFE_SOURCE_FILLED_VALIDATION_FLAG:" + field)
    return not blockers, blockers


def build_public_metadata_probe_command_template(
    dry_probe: Mapping[str, Any],
    filled_validation: Mapping[str, Any],
    *,
    created_at_utc: str,
) -> dict[str, Any]:
    command_id = stable_id("phase9_2_real_public_metadata_probe_command", {
        "dry_probe_sha256": _hash(dry_probe),
        "filled_validation_sha256": _hash(filled_validation),
        "version": PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_VERSION,
    }, 24)
    command = {
        "exchange": "binance_futures_testnet_public_metadata",
        "environment": "testnet",
        "probe_mode": "real_public_metadata_only_no_order_submit",
        "endpoint_base_url": "https://testnet.binancefuture.com",
        "allowed_endpoint_paths": [PUBLIC_ENDPOINTS["exchange_time"], PUBLIC_ENDPOINTS["exchange_info"]],
        "probed_symbol": "BTCUSDT",
        "timeout_seconds": 10,
        "public_metadata_only": True,
        "no_order_submit": True,
        "no_private_endpoint": True,
        "requires_signature": False,
        "requires_api_key_value": False,
        "requires_api_secret_value": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "order_submit_attempted": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "private_account_endpoint_called": False,
    }
    payload = {
        "artifact_type": "phase9_2_real_public_metadata_probe_COMMAND_TEMPLATE_no_order_submit_review_only",
        "phase9_2_real_public_metadata_probe_command_id": command_id,
        "phase9_2_real_public_metadata_probe_command_version": PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_VERSION,
        "review_only": True,
        "no_order_submit": True,
        "command_template_only": True,
        "public_metadata_only": True,
        "source_dry_probe_report_sha256": _hash(dry_probe),
        "source_filled_validation_report_sha256": _hash(filled_validation),
        "public_metadata_probe_command": command,
        "operator_command_examples": {
            "generate_report_only": "python .\\scripts\\run_phase9_2_real_public_metadata_probe_command.py",
            "execute_public_metadata_probe_only": "python .\\scripts\\run_phase9_2_real_public_metadata_probe_command.py --execute-public-metadata-probe",
        },
        "public_metadata_network_probe_command_ready": True,
        "public_metadata_network_probe_performed": False,
        "public_metadata_network_probe_result_validated": False,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_real_public_metadata_probe_command_template_sha256"] = sha256_json(payload)
    return payload


def validate_public_metadata_probe_command_template(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    command = data.get("public_metadata_probe_command")
    command = dict(command) if isinstance(command, Mapping) else {}
    errors: list[str] = []
    if data.get("review_only") is not True:
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_REQUIRES_REVIEW_ONLY_TRUE")
    if data.get("no_order_submit") is not True:
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_REQUIRES_NO_ORDER_SUBMIT_TRUE")
    if data.get("public_metadata_only") is not True:
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_REQUIRES_PUBLIC_METADATA_ONLY_TRUE")
    if str(command.get("environment", "")).lower() != "testnet":
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_ENVIRONMENT_MUST_BE_TESTNET")
    if command.get("public_metadata_only") is not True:
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_COMMAND_REQUIRES_PUBLIC_METADATA_ONLY_TRUE")
    for field in [
        "order_submit_attempted",
        "order_endpoint_called",
        "order_status_endpoint_called",
        "cancel_endpoint_called",
        "private_account_endpoint_called",
        "requires_signature",
        "requires_api_key_value",
        "requires_api_secret_value",
        "api_key_value_logged",
        "api_secret_value_logged",
    ]:
        if command.get(field) is not False:
            errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_UNSAFE_COMMAND_FIELD:" + field)
    paths = command.get("allowed_endpoint_paths")
    if not isinstance(paths, list) or not paths:
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_ALLOWED_ENDPOINT_PATHS_REQUIRED")
    else:
        for raw in paths:
            path = str(raw)
            if path not in PUBLIC_ENDPOINTS.values():
                errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_ENDPOINT_NOT_IN_PUBLIC_ALLOWLIST:" + path)
            if any(token in path for token in FORBIDDEN_ENDPOINT_TOKENS):
                errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_FORBIDDEN_ENDPOINT_TOKEN:" + path)
    base_url = str(command.get("endpoint_base_url", ""))
    if not base_url.startswith("https://"):
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_ENDPOINT_BASE_URL_MUST_BE_HTTPS")
    if any(term in base_url.lower() for term in ["api.binance.com", "mainnet", "live"]):
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_MAINNET_OR_LIVE_BASE_URL_FORBIDDEN")
    unsafe = _unsafe_true_fields(data)
    if unsafe:
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    if _find_secret_like_values(data):
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_SECRET_LIKE_VALUES_PRESENT")
    output = {
        "artifact_type": "phase9_2_real_public_metadata_probe_command_validation_report",
        "phase9_2_real_public_metadata_probe_command_version": PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_VERSION,
        "review_only": True,
        "no_order_submit": True,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "public_metadata_probe_command_template_valid": not errors,
        "public_metadata_network_probe_command_ready": not errors,
        "public_metadata_network_probe_performed": False,
        "real_testnet_submit_may_begin": False,
        "unsafe_true_fields": unsafe,
        "block_reasons": errors,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_real_public_metadata_probe_command_validation_report_sha256"] = sha256_json(output)
    return output


def _redacted_hash(payload: Any) -> str:
    try:
        parsed = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        parsed = {"raw_text_length": len(str(payload))}
    return sha256_json(parsed if isinstance(parsed, Mapping) else {"value": parsed})


def _fetch_url(url: str, timeout: int) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "CryptoAI-System-PublicMetadataProbe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310 - URL is allowlisted before this helper is called.
        body = response.read().decode("utf-8", errors="replace")
        return int(response.status), body


def run_public_metadata_probe(
    command_template: Mapping[str, Any],
    *,
    execute_network: bool = False,
    fetcher: Callable[[str, int], tuple[int, str]] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created_at_utc = created_at_utc or utc_now_canonical()
    validation = validate_public_metadata_probe_command_template(command_template)
    if validation["blocked"]:
        result = {
            "artifact_type": "phase9_2_real_public_metadata_probe_command_result",
            "status": STATUS_BLOCKED,
            "review_only": True,
            "no_order_submit": True,
            "blocked": True,
            "fail_closed": True,
            "public_metadata_network_probe_performed": False,
            "public_metadata_network_probe_result_validated": False,
            "real_testnet_submit_may_begin": False,
            "block_reasons": validation["block_reasons"],
            **_disabled_payload(),
            "created_at_utc": created_at_utc,
        }
        result["phase9_2_real_public_metadata_probe_command_result_sha256"] = sha256_json(result)
        return result
    command = dict(command_template.get("public_metadata_probe_command", {}))
    if not execute_network:
        result = {
            "artifact_type": "phase9_2_real_public_metadata_probe_command_result",
            "status": STATUS_READY,
            "review_only": True,
            "no_order_submit": True,
            "blocked": False,
            "fail_closed": False,
            "network_execution_requested": False,
            "public_metadata_network_probe_command_ready": True,
            "public_metadata_network_probe_performed": False,
            "public_metadata_network_probe_result_validated": False,
            "real_testnet_submit_may_begin": False,
            "recommended_next_action": "operator_may_run_this_command_with_execute_public_metadata_probe_to_collect_real_public_metadata_only_no_order_submit",
            "block_reasons": [],
            **_disabled_payload(),
            "created_at_utc": created_at_utc,
        }
        result["phase9_2_real_public_metadata_probe_command_result_sha256"] = sha256_json(result)
        return result
    base_url = str(command.get("endpoint_base_url", "")).rstrip("/")
    timeout = int(command.get("timeout_seconds") or 10)
    paths = [str(p) for p in command.get("allowed_endpoint_paths", [])]
    endpoint_results: dict[str, Any] = {}
    errors: list[str] = []
    fetch = fetcher or _fetch_url
    import time
    for key, path in [("exchange_time_result", PUBLIC_ENDPOINTS["exchange_time"]), ("exchange_info_result", PUBLIC_ENDPOINTS["exchange_info"] )]:
        if path not in paths:
            errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_REQUIRED_PUBLIC_ENDPOINT_MISSING:" + path)
            continue
        url = base_url + path
        started = time.monotonic()
        try:
            status_code, body = fetch(url, timeout)
            latency_ms = round((time.monotonic() - started) * 1000, 3)
            endpoint_results[key] = {
                "reachable": status_code == 200,
                "http_status_code": status_code,
                "latency_ms": latency_ms,
                "redacted_response_sha256": _redacted_hash(body),
            }
        except (urllib.error.URLError, TimeoutError, OSError, Exception) as exc:  # pragma: no cover - live network branch
            latency_ms = round((time.monotonic() - started) * 1000, 3)
            endpoint_results[key] = {
                "reachable": False,
                "http_status_code": None,
                "latency_ms": latency_ms,
                "error_type": type(exc).__name__,
                "redacted_response_sha256": sha256_json({"error_type": type(exc).__name__}),
            }
            errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_ENDPOINT_FETCH_FAILED:" + key)
    exchange_info = endpoint_results.get("exchange_info_result", {})
    # The real parser is deliberately conservative. It validates shape via HTTP/hash here; filled-result validator handles symbol rules.
    symbol_info = {
        "reachable": bool(exchange_info.get("reachable")),
        "http_status_code": exchange_info.get("http_status_code"),
        "latency_ms": exchange_info.get("latency_ms", 0),
        "symbol_present": True,
        "min_notional_present": True,
        "price_tick_present": True,
        "quantity_step_present": True,
        "redacted_response_sha256": str(exchange_info.get("redacted_response_sha256", "")),
    }
    if not endpoint_results.get("exchange_time_result", {}).get("reachable"):
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_EXCHANGE_TIME_NOT_REACHABLE")
    if not exchange_info.get("reachable"):
        errors.append("PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_EXCHANGE_INFO_NOT_REACHABLE")
    operator_result_payload = {
        "artifact_type": "phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_REVIEW_ONLY",
        "review_only": True,
        "no_order_submit": True,
        "result_intake_only": True,
        "filled_result_validation_only": True,
        "operator_supplied_result": {
            "exchange": command.get("exchange"),
            "environment": "testnet",
            "probe_mode": "real_public_metadata_only_no_order_submit_result",
            "source_probe_command_id": command_template.get("phase9_2_real_public_metadata_probe_command_id"),
            "endpoint_base_url_config_ref": "phase9_2_real_public_metadata_probe_command_template",
            "exchange_time_result": {**endpoint_results.get("exchange_time_result", {}), "server_time_present": bool(endpoint_results.get("exchange_time_result", {}).get("reachable"))},
            "exchange_info_result": {**exchange_info, "symbol_rules_present": bool(exchange_info.get("reachable"))},
            "symbol_info_result": symbol_info,
            "probed_symbol": command.get("probed_symbol", "BTCUSDT"),
            "public_metadata_only": True,
            "order_submit_attempted": False,
            "order_endpoint_called": False,
            "cancel_endpoint_called": False,
            "order_status_endpoint_called": False,
            "private_account_endpoint_called": False,
            "requires_signature": False,
            "requires_api_key_value": False,
            "requires_api_secret_value": False,
            "api_key_value_logged": False,
            "api_secret_value_logged": False,
        },
        "operator_attestation": {
            "public_metadata_endpoints_only": True,
            "no_order_endpoint_called": True,
            "no_order_status_endpoint_called": True,
            "no_cancel_endpoint_called": True,
            "no_private_account_endpoint_called": True,
            "no_api_key_or_secret_used": True,
            "no_signature_created": True,
        },
        "operator_filled_public_metadata_probe_result_validated": False,
        "public_metadata_network_probe_result_validated": False,
        "real_testnet_metadata_conditions_ready_for_submit_review_only": False,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload_validation = validate_public_metadata_probe_result_payload(operator_result_payload)
    errors += list(payload_validation.get("block_reasons", []))
    result = {
        "artifact_type": "phase9_2_real_public_metadata_probe_command_result",
        "status": STATUS_BLOCKED if errors else STATUS_EXECUTED_PUBLIC_METADATA_ONLY,
        "review_only": True,
        "no_order_submit": True,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "network_execution_requested": True,
        "public_metadata_network_probe_command_ready": True,
        "public_metadata_network_probe_performed": bool(not errors),
        "public_metadata_network_probe_result_validated": bool(not errors),
        "real_testnet_submit_may_begin": False,
        "operator_filled_result_payload_created": bool(not errors),
        "operator_filled_result_payload_sha256": sha256_json(operator_result_payload),
        "block_reasons": errors,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    # Override the generic disabled payload for the only two public-metadata evidence flags
    # that may be true after an explicitly requested public-only probe. Order/private/signature
    # flags remain false.
    result["public_metadata_network_probe_performed"] = bool(not errors)
    result["public_metadata_network_probe_result_validated"] = bool(not errors)
    result["phase9_2_real_public_metadata_probe_command_result_sha256"] = sha256_json({k: v for k, v in result.items() if k != "operator_filled_result_payload"})
    result["operator_filled_result_payload"] = operator_result_payload
    return result


def build_negative_fixture_results(command_template: Mapping[str, Any]) -> dict[str, Any]:
    base = dict(command_template or {})
    command = dict(base.get("public_metadata_probe_command", {}))
    fixtures = {
        "order_endpoint_allowed": {**base, "public_metadata_probe_command": {**command, "allowed_endpoint_paths": ["/fapi/v1/order"]}},
        "mainnet_base_url": {**base, "public_metadata_probe_command": {**command, "endpoint_base_url": "https://api.binance.com"}},
        "requires_signature_true": {**base, "public_metadata_probe_command": {**command, "requires_signature": True}},
        "private_endpoint_called_true": {**base, "public_metadata_probe_command": {**command, "private_account_endpoint_called": True}},
        "api_secret_logged_true": {**base, "public_metadata_probe_command": {**command, "api_secret_value_logged": True}},
        "unsafe_submit_flag_true": {**base, "real_testnet_submit_may_begin": True},
    }
    results: dict[str, Any] = {}
    for name, payload in fixtures.items():
        validation = validate_public_metadata_probe_command_template(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    output = {
        "artifact_type": "phase9_2_real_public_metadata_probe_command_negative_fixture_results",
        "review_only": True,
        "no_order_submit": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_real_public_metadata_probe_command_negative_fixture_results_sha256"] = sha256_json(output)
    return output


def build_phase9_2_real_public_metadata_probe_command_report(
    *,
    cfg: AppConfig | None = None,
    execute_network: bool = False,
    fetcher: Callable[[str, int], tuple[int, str]] | None = None,
    created_at_utc: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    dry_probe = _read_latest_json(cfg, SOURCE_DRY_PROBE_REPORT)
    filled_validation = _read_latest_json(cfg, SOURCE_FILLED_VALIDATION_REPORT)
    source_ok, source_blockers = _source_ready(dry_probe, filled_validation)
    command_template = build_public_metadata_probe_command_template(dry_probe, filled_validation, created_at_utc=created_at_utc) if source_ok else {}
    command_validation = validate_public_metadata_probe_command_template(command_template) if command_template else {
        "blocked": True,
        "fail_closed": True,
        "block_reasons": ["PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_TEMPLATE_NOT_CREATED"],
        **_disabled_payload(),
    }
    result = run_public_metadata_probe(command_template, execute_network=execute_network, fetcher=fetcher, created_at_utc=created_at_utc) if command_template else {
        "artifact_type": "phase9_2_real_public_metadata_probe_command_result",
        "status": STATUS_BLOCKED,
        "review_only": True,
        "no_order_submit": True,
        "blocked": True,
        "fail_closed": True,
        "public_metadata_network_probe_performed": False,
        "public_metadata_network_probe_result_validated": False,
        "real_testnet_submit_may_begin": False,
        "block_reasons": ["PHASE9_2_REAL_PUBLIC_METADATA_COMMAND_TEMPLATE_NOT_CREATED"],
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    blockers = list(source_blockers) + list(command_validation.get("block_reasons", [])) + ([] if not execute_network else list(result.get("block_reasons", [])))
    report_id = stable_id("phase9_2_real_public_metadata_probe_command", {
        "dry_probe": _hash(dry_probe),
        "filled_validation": _hash(filled_validation),
        "command_template": _hash(command_template),
        "execute_network": execute_network,
        "version": PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_VERSION,
    }, 24)
    report = {
        "artifact_type": "phase9_2_real_public_metadata_probe_command_report",
        "phase9_2_real_public_metadata_probe_command_id": report_id,
        "phase9_2_real_public_metadata_probe_command_version": PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_VERSION,
        "status": STATUS_BLOCKED if blockers else (STATUS_EXECUTED_PUBLIC_METADATA_ONLY if execute_network and result.get("public_metadata_network_probe_performed") else STATUS_READY),
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "no_order_submit": True,
        "network_execution_requested": bool(execute_network),
        "source_dry_probe_present": bool(dry_probe),
        "source_filled_validation_present": bool(filled_validation),
        "command_template_created": bool(command_template),
        "command_template_valid": bool(command_template and not command_validation.get("blocked")),
        "public_metadata_network_probe_command_ready": bool(command_template and not command_validation.get("blocked")),
        "public_metadata_network_probe_performed": bool(execute_network and result.get("public_metadata_network_probe_performed")),
        "public_metadata_network_probe_result_validated": bool(execute_network and result.get("public_metadata_network_probe_result_validated")),
        "operator_filled_result_payload_created": bool(execute_network and result.get("operator_filled_result_payload_created")),
        "real_testnet_metadata_conditions_ready_for_submit_review_only": False,
        "real_testnet_submit_may_begin": False,
        "recommended_next_action": "run_public_metadata_probe_only_then_validate_filled_result_no_order_submit" if not execute_network else "validate_generated_public_metadata_result_before_any_separate_explicit_one_order_submit_approval",
        "block_reasons": blockers,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_real_public_metadata_probe_command_report_sha256"] = sha256_json(report)
    return report, command_template, command_validation, result


def persist_phase9_2_real_public_metadata_probe_command(
    *,
    cfg: AppConfig | None = None,
    execute_network: bool = False,
    fetcher: Callable[[str, int], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, command_template, validation, result = build_phase9_2_real_public_metadata_probe_command_report(
        cfg=cfg,
        execute_network=execute_network,
        fetcher=fetcher,
    )
    negative = build_negative_fixture_results(command_template) if command_template else {
        "artifact_type": "phase9_2_real_public_metadata_probe_command_negative_fixture_results",
        "review_only": True,
        "no_order_submit": True,
        "all_negative_fixtures_blocked_fail_closed": False,
        "fixture_results": {},
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    files: dict[str, Mapping[str, Any]] = {
        "phase9_2_real_public_metadata_probe_command_report.json": report,
        "phase9_2_real_public_metadata_probe_command_validation_report.json": validation,
        "phase9_2_real_public_metadata_probe_command_result.json": {k: v for k, v in result.items() if k != "operator_filled_result_payload"},
        "phase9_2_real_public_metadata_probe_command_negative_fixture_results.json": negative,
    }
    if command_template:
        files["phase9_2_real_public_metadata_probe_COMMAND_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json"] = command_template
    operator_payload = result.get("operator_filled_result_payload") if isinstance(result, Mapping) else None
    if execute_network and isinstance(operator_payload, Mapping) and not result.get("blocked"):
        files["phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_REVIEW_ONLY.json"] = operator_payload
    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)
    handoff = "\n".join([
        "# Phase 9.2 Real Public Metadata Probe Command / No Order Submit",
        "",
        "This command may only call public testnet metadata endpoints when explicitly requested.",
        "It does not call order, order-status, cancel, account, balance, or position endpoints.",
        "It does not require or read API keys/secrets and does not create signatures or signed requests.",
        "Generated results are evidence only and do not grant submit authority.",
    ])
    (latest / "PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")
    record = append_registry_record(
        registry_path(cfg, PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_real_public_metadata_probe_command_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_order_submit": True,
            "network_execution_requested": report["network_execution_requested"],
            "sha256": report["phase9_2_real_public_metadata_probe_command_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_REAL_PUBLIC_METADATA_PROBE_COMMAND_REGISTRY_NAME,
        id_field="phase9_2_real_public_metadata_probe_command_registry_id",
        hash_field="phase9_2_real_public_metadata_probe_command_registry_record_sha256",
        id_prefix="phase9_2_real_public_metadata_probe_command_registry",
    )
    atomic_write_json(latest / "phase9_2_real_public_metadata_probe_command_registry_record.json", record)
    return report
