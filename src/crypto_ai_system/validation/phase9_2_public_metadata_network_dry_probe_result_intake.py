from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_2_real_testnet_endpoint_adapter_preflight import _hash
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool
from crypto_ai_system.validation.phase9_2_real_testnet_network_dry_probe import NETWORK_DRY_PROBE_FALSE_FLAGS

PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_VERSION = "phase9_2_public_metadata_network_dry_probe_result_intake_v1"
PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_REGISTRY_NAME = "phase9_2_public_metadata_network_dry_probe_result_intake_registry"
STATUS_RECORDED = "PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_RECORDED_NO_ORDER_SUBMIT_REVIEW_ONLY"
STATUS_BLOCKED = "PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_BLOCKED_FAIL_CLOSED"
SOURCE_DRY_PROBE_FILE = "phase9_2_real_testnet_network_dry_probe_report.json"

RESULT_FALSE_FLAGS = sorted(set(NETWORK_DRY_PROBE_FALSE_FLAGS + [
    "public_metadata_network_probe_result_validated",
    "real_network_order_probe_performed",
    "private_network_probe_performed",
    "network_order_status_probe_performed",
    "network_cancel_probe_performed",
    "real_testnet_submit_may_begin",
]))

REQUIRED_RESULT_FIELDS = [
    "exchange",
    "environment",
    "probe_mode",
    "source_probe_command_id",
    "endpoint_base_url_config_ref",
    "exchange_time_result",
    "exchange_info_result",
    "symbol_info_result",
    "probed_symbol",
    "public_metadata_only",
    "order_submit_attempted",
    "order_endpoint_called",
    "cancel_endpoint_called",
    "order_status_endpoint_called",
    "private_account_endpoint_called",
    "requires_signature",
    "requires_api_key_value",
    "requires_api_secret_value",
    "api_key_value_logged",
    "api_secret_value_logged",
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


def _disabled_payload() -> dict[str, bool]:
    return {field: False for field in RESULT_FALSE_FLAGS}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return sorted(field for field in RESULT_FALSE_FLAGS if _safe_bool(data.get(field)))


def _source_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": "phase9_2_real_testnet_network_dry_probe_report",
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _hash(data),
        "network_dry_probe_ready_for_operator_no_order_command": data.get("network_dry_probe_ready_for_operator_no_order_command"),
        "public_metadata_network_probe_performed": data.get("public_metadata_network_probe_performed"),
        "real_testnet_submit_may_begin": data.get("real_testnet_submit_may_begin"),
    }


def _source_ready(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    data = dict(payload or {})
    blockers: list[str] = []
    if not data:
        return False, ["PHASE9_2_PUBLIC_METADATA_RESULT_SOURCE_DRY_PROBE_REPORT_MISSING"]
    if data.get("blocked") is True or data.get("fail_closed") is True:
        blockers.append("PHASE9_2_PUBLIC_METADATA_RESULT_SOURCE_DRY_PROBE_BLOCKED")
    if data.get("network_dry_probe_ready_for_operator_no_order_command") is not True:
        blockers.append("PHASE9_2_PUBLIC_METADATA_RESULT_REQUIRES_DRY_PROBE_READY")
    if data.get("public_metadata_network_probe_performed") is not False:
        blockers.append("PHASE9_2_PUBLIC_METADATA_RESULT_SOURCE_MUST_NOT_PRETEND_PROBE_PERFORMED")
    for field in [
        "actual_order_submission_performed",
        "real_exchange_endpoint_call_performed",
        "order_endpoint_called",
        "order_status_endpoint_called",
        "cancel_endpoint_called",
        "private_account_endpoint_called",
        "balance_endpoint_called",
        "position_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
    ]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_PUBLIC_METADATA_RESULT_UNSAFE_SOURCE_FLAG:{field}")
    unsafe = _unsafe_true_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_PUBLIC_METADATA_RESULT_SOURCE_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    return not blockers, blockers


def build_public_metadata_probe_result_template(source_dry_probe: Mapping[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    template_id = stable_id("phase9_2_public_metadata_probe_result_template", {
        "source_dry_probe_sha256": _hash(source_dry_probe),
        "version": PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_VERSION,
    }, 24)
    payload = {
        "artifact_type": "phase9_2_public_metadata_network_dry_probe_result_TEMPLATE_no_order_submit_review_only",
        "phase9_2_public_metadata_network_dry_probe_result_template_id": template_id,
        "phase9_2_public_metadata_network_dry_probe_result_intake_version": PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_VERSION,
        "review_only": True,
        "no_order_submit": True,
        "result_intake_only": True,
        "source_dry_probe_report_sha256": _hash(source_dry_probe),
        "required_result_fields": REQUIRED_RESULT_FIELDS,
        "operator_supplied_result_placeholder": {
            "exchange": "CONFIGURED_TESTNET_EXCHANGE_REVIEW_ONLY",
            "environment": "testnet",
            "probe_mode": "public_metadata_read_only_no_order_submit_result",
            "source_probe_command_id": "OPERATOR_PUBLIC_METADATA_PROBE_COMMAND_ID_PLACEHOLDER",
            "endpoint_base_url_config_ref": "CAS_TESTNET_ENDPOINT_BASE_URL_REF_ONLY",
            "exchange_time_result": {
                "reachable": True,
                "http_status_code": 200,
                "latency_ms": 0,
                "server_time_present": True,
                "redacted_response_sha256": "PLACEHOLDER_SHA256_OF_REDACTED_PUBLIC_RESPONSE",
            },
            "exchange_info_result": {
                "reachable": True,
                "http_status_code": 200,
                "latency_ms": 0,
                "symbol_rules_present": True,
                "redacted_response_sha256": "PLACEHOLDER_SHA256_OF_REDACTED_PUBLIC_RESPONSE",
            },
            "symbol_info_result": {
                "reachable": True,
                "http_status_code": 200,
                "latency_ms": 0,
                "symbol_present": True,
                "min_notional_present": True,
                "price_tick_present": True,
                "quantity_step_present": True,
                "redacted_response_sha256": "PLACEHOLDER_SHA256_OF_REDACTED_PUBLIC_RESPONSE",
            },
            "probed_symbol": "BTCUSDT",
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
        "forbidden_result_fields": [
            "api_key",
            "api_secret",
            "signature",
            "private_key",
            "passphrase",
            "order_id",
            "client_order_id",
            "balance",
            "position",
            "open_orders",
        ],
        "public_metadata_network_probe_result_validated": False,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_public_metadata_network_dry_probe_result_template_sha256"] = sha256_json(payload)
    return payload


def validate_public_metadata_probe_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    result = data.get("operator_supplied_result")
    result = dict(result) if isinstance(result, Mapping) else dict(data.get("operator_supplied_result_placeholder", {})) if isinstance(data.get("operator_supplied_result_placeholder"), Mapping) else {}
    unsafe = _unsafe_true_fields(data) + [f for f in [
        "order_submit_attempted",
        "order_endpoint_called",
        "cancel_endpoint_called",
        "order_status_endpoint_called",
        "private_account_endpoint_called",
        "requires_signature",
        "requires_api_key_value",
        "requires_api_secret_value",
        "api_key_value_logged",
        "api_secret_value_logged",
    ] if result.get(f) is True]
    unsafe = sorted(set(unsafe))
    secret_like = _find_secret_like_values(data)
    errors: list[str] = []
    if data.get("review_only") is not True:
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_REQUIRES_REVIEW_ONLY_TRUE")
    if data.get("no_order_submit") is not True:
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_REQUIRES_NO_ORDER_SUBMIT_TRUE")
    if data.get("result_intake_only") is not True:
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_REQUIRES_RESULT_INTAKE_ONLY_TRUE")
    missing = [field for field in REQUIRED_RESULT_FIELDS if field not in result or result.get(field) in (None, "", [])]
    if missing:
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_MISSING_FIELDS:" + ",".join(missing))
    if str(result.get("environment", "")).lower() != "testnet":
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_ENVIRONMENT_MUST_BE_TESTNET")
    if any(term in str(result.get("environment", "")).lower() for term in ["live", "mainnet"]):
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_LIVE_OR_MAINNET_ENV_FORBIDDEN")
    if result.get("public_metadata_only") is not True:
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_REQUIRES_PUBLIC_METADATA_ONLY_TRUE")
    for endpoint in ["exchange_time_result", "exchange_info_result", "symbol_info_result"]:
        item = result.get(endpoint)
        if not isinstance(item, Mapping):
            errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_MISSING_ENDPOINT_RESULT:" + endpoint)
            continue
        if item.get("reachable") is not True:
            errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_ENDPOINT_NOT_REACHABLE:" + endpoint)
        if item.get("http_status_code") not in (200, "200"):
            errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_ENDPOINT_HTTP_STATUS_NOT_200:" + endpoint)
        if not isinstance(item.get("latency_ms"), (int, float)) or item.get("latency_ms") < 0:
            errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_INVALID_LATENCY:" + endpoint)
    symbol_info = result.get("symbol_info_result") if isinstance(result.get("symbol_info_result"), Mapping) else {}
    for field in ["symbol_present", "min_notional_present", "price_tick_present", "quantity_step_present"]:
        if symbol_info.get(field) is not True:
            errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_SYMBOL_RULE_FIELD_MISSING:" + field)
    for field in [
        "order_submit_attempted",
        "order_endpoint_called",
        "cancel_endpoint_called",
        "order_status_endpoint_called",
        "private_account_endpoint_called",
        "requires_signature",
        "requires_api_key_value",
        "requires_api_secret_value",
        "api_key_value_logged",
        "api_secret_value_logged",
    ]:
        if result.get(field) is not False:
            errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_UNSAFE_RESULT_FIELD:" + field)
    if unsafe:
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    if secret_like:
        errors.append("PHASE9_2_PUBLIC_METADATA_RESULT_SECRET_LIKE_VALUES_PRESENT")
    return {
        "artifact_type": "phase9_2_public_metadata_network_dry_probe_result_intake_validation_report",
        "phase9_2_public_metadata_network_dry_probe_result_intake_version": PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_VERSION,
        "review_only": True,
        "no_order_submit": True,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "public_metadata_network_probe_result_payload_valid": not errors,
        "missing_result_fields": missing if 'missing' in locals() else REQUIRED_RESULT_FIELDS,
        "unsafe_true_fields": unsafe,
        "secret_like_values_detected": bool(secret_like),
        "block_reasons": errors,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }


def build_negative_fixture_results() -> dict[str, Any]:
    base = build_public_metadata_probe_result_template({}, created_at_utc="2026-01-01T00:00:00Z")
    fixtures = {}
    for name, mutate in {
        "mainnet_environment": {"environment": "mainnet"},
        "order_submit_attempted_true": {"order_submit_attempted": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "private_account_endpoint_called_true": {"private_account_endpoint_called": True},
        "signature_required_true": {"requires_signature": True},
        "api_secret_logged_true": {"api_secret_value_logged": True},
        "symbol_rule_missing": {"symbol_info_result": {"reachable": True, "http_status_code": 200, "latency_ms": 1, "symbol_present": True, "min_notional_present": False, "price_tick_present": True, "quantity_step_present": True}},
    }.items():
        p = {**base, "operator_supplied_result": {**base["operator_supplied_result_placeholder"], **mutate}}
        fixtures[name] = p
    secret_fixture = {**base, "operator_supplied_result": dict(base["operator_supplied_result_placeholder"]), "api_secret": "SECRET_VALUE_SHOULD_NOT_BE_HERE"}
    fixtures["secret_like_value"] = secret_fixture
    results: dict[str, Any] = {}
    for name, payload in fixtures.items():
        validation = validate_public_metadata_probe_result_payload(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    output = {
        "artifact_type": "phase9_2_public_metadata_network_dry_probe_result_intake_negative_fixture_results",
        "review_only": True,
        "no_order_submit": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_public_metadata_network_dry_probe_result_intake_negative_fixture_results_sha256"] = sha256_json(output)
    return output


def build_phase9_2_public_metadata_network_dry_probe_result_intake_report(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    source = _read_latest_json(cfg, SOURCE_DRY_PROBE_FILE)
    source_ready, source_blockers = _source_ready(source)
    template = build_public_metadata_probe_result_template(source, created_at_utc=created_at_utc) if source_ready else {}
    validation = validate_public_metadata_probe_result_payload(template) if template else {}
    blockers = list(source_blockers) + (validation.get("block_reasons", []) if validation else [])
    report_id = stable_id("phase9_2_public_metadata_network_dry_probe_result_intake", {
        "source": _source_summary(source),
        "template_hash": template.get("phase9_2_public_metadata_network_dry_probe_result_template_sha256") if template else None,
    }, 24)
    report = {
        "artifact_type": "phase9_2_public_metadata_network_dry_probe_result_intake_report",
        "phase9_2_public_metadata_network_dry_probe_result_intake_id": report_id,
        "phase9_2_public_metadata_network_dry_probe_result_intake_version": PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_VERSION,
        "status": STATUS_BLOCKED if blockers else STATUS_RECORDED,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "no_order_submit": True,
        "result_intake_only": True,
        "source_dry_probe_summary": _source_summary(source),
        "source_blockers": source_blockers,
        "result_template_created": bool(template),
        "result_template_payload_valid": bool(validation and validation.get("public_metadata_network_probe_result_payload_valid")),
        "public_metadata_network_probe_result_intake_ready": bool(template and validation and not blockers),
        "public_metadata_network_probe_result_validated": False,
        "real_testnet_submit_may_begin": False,
        "real_testnet_endpoint_adapter_attached": False,
        "order_endpoint_calls_allowed": False,
        "signature_creation_allowed": False,
        "http_transmission_allowed_for_order": False,
        "block_reasons": blockers,
        "recommended_next_action": "operator_may_fill_public_metadata_probe_result_template_for_validation_no_order_submit_before_any_runtime_submit",
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_public_metadata_network_dry_probe_result_intake_report_sha256"] = sha256_json(report)
    return report, template


def persist_phase9_2_public_metadata_network_dry_probe_result_intake(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, template = build_phase9_2_public_metadata_network_dry_probe_result_intake_report(cfg=cfg)
    validation = validate_public_metadata_probe_result_payload(template) if template else validate_public_metadata_probe_result_payload({})
    negative = build_negative_fixture_results()
    files: dict[str, Mapping[str, Any]] = {
        "phase9_2_public_metadata_network_dry_probe_result_intake_report.json": report,
        "phase9_2_public_metadata_network_dry_probe_result_intake_validation_report.json": validation,
        "phase9_2_public_metadata_network_dry_probe_result_intake_negative_fixture_results.json": negative,
    }
    if template:
        files["phase9_2_public_metadata_network_dry_probe_RESULT_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json"] = template
    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)
    handoff = "\n".join([
        "# Phase 9.2 Public Metadata Network Dry Probe Result Intake / No Order Submit",
        "",
        "This packet validates operator-supplied public metadata dry probe results only.",
        "It does not call order, cancel, order-status, account, balance, or position endpoints.",
        "It does not create signatures, read API secrets, send signed requests, or submit orders.",
        "Validated public metadata results are evidence only and do not grant runtime submit authority.",
    ])
    (latest / "PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")
    record = append_registry_record(
        registry_path(cfg, PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_public_metadata_network_dry_probe_result_intake_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_order_submit": True,
            "sha256": report["phase9_2_public_metadata_network_dry_probe_result_intake_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_REGISTRY_NAME,
        id_field="phase9_2_public_metadata_network_dry_probe_result_intake_registry_id",
        hash_field="phase9_2_public_metadata_network_dry_probe_result_intake_registry_record_sha256",
        id_prefix="phase9_2_public_metadata_network_dry_probe_result_intake_registry",
    )
    atomic_write_json(latest / "phase9_2_public_metadata_network_dry_probe_result_intake_registry_record.json", record)
    return report
