from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_VERSION = "p48_local_runtime_adapter_connector_v1"
P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_REGISTRY_NAME = "p48_local_runtime_adapter_connector_registry"
STATUS_READY_REVIEW_ONLY_NO_SUBMIT = "P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_READY_REVIEW_ONLY_NO_SUBMIT"
STATUS_BLOCKED_FAIL_CLOSED = "P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_BLOCKED_FAIL_CLOSED"

_ALLOWED_ENVIRONMENTS = {"testnet"}
_ALLOWED_VENUES = {"binance_futures_testnet"}
_ALLOWED_SYMBOLS = {"BTCUSDT"}
_FORBIDDEN_SECRET_FIELDS = {
    "api_key",
    "api_secret",
    "secret",
    "secret_value",
    "private_key",
    "passphrase",
    "binance_api_key",
    "binance_api_secret",
}
_FORBIDDEN_SCOPE_TOKENS = ("mainnet", "live_trade", "withdraw", "transfer", "admin", "margin_mutation", "leverage_mutation")


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _execution_false_payload() -> dict[str, bool]:
    payload = default_execution_flag_state()
    payload.update(
        {
            "actual_testnet_order_submitted": False,
            "actual_live_order_submitted": False,
            "actual_order_submission_performed": False,
            "external_order_submission_performed": False,
            "order_endpoint_called": False,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "api_key_value_logged": False,
            "api_secret_value_logged": False,
            "real_endpoint_adapter_attached": False,
            "local_runtime_connector_attached": False,
            "runtime_network_call_allowed_by_operator": False,
        }
    )
    return payload


@dataclass(frozen=True)
class LocalRuntimeAdapterConnectorConfig:
    connector_id: str = "p48_local_runtime_adapter_connector_TEMPLATE_NO_SUBMIT"
    connector_version: str = P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_VERSION
    connector_scope: str = "separate_local_runtime_package_only"
    review_package_default_no_submit: bool = True
    external_runtime_only: bool = True
    real_adapter_code_included_in_review_package: bool = False
    local_runtime_connector_attached: bool = False
    can_submit_orders_by_default: bool = False
    network_calls_allowed_in_review_package: bool = False
    venue: str = "binance_futures_testnet"
    environment: str = "testnet"
    symbol: str = "BTCUSDT"
    max_order_count: int = 1
    max_notional_usdt: str = "LOW_NOTIONAL_OPERATOR_DEFINED"
    adapter_protocol_ref: str = "crypto_ai_system.execution.single_signed_testnet_submit_runtime_action.SignedTestnetSubmitAdapter"
    adapter_factory_ref: str = "EXTERNAL_RUNTIME_ONLY_SET_BY_OPERATOR"
    external_runtime_entrypoint_ref: str = "EXTERNAL_RUNTIME_ONLY_NOT_INCLUDED_IN_REVIEW_PACKAGE"
    order_endpoint_ref: str = "TESTNET_PRIVATE_ORDER_ENDPOINT_REF_ONLY"
    status_endpoint_ref: str = "TESTNET_PRIVATE_STATUS_ENDPOINT_REF_ONLY"
    cancel_endpoint_ref: str = "TESTNET_PRIVATE_CANCEL_ENDPOINT_REF_ONLY"
    request_signing_boundary: str = "external_runtime_process_memory_only"
    secret_binding_mode: str = "metadata_reference_only_in_review_package"
    secret_reference_id: str = "OPERATOR_SUPPLIED_TESTNET_SECRET_REFERENCE_ID"
    key_fingerprint_sha256: str = "0" * 64
    p6_external_runtime_preflight_required: bool = True
    p7_real_post_submit_evidence_required_after_submit: bool = True
    p8_repeated_clean_sessions_required_before_live_canary: bool = True
    operator_arming_phrase_required: bool = True
    duplicate_submit_lock_required: bool = True
    idempotency_key_required: bool = True
    post_submit_relock_required: bool = True
    redacted_evidence_export_required: bool = True
    raw_secret_values_allowed_in_connector_config: bool = False
    raw_exchange_payload_allowed_in_review_package: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["connector_config_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LocalRuntimeAdapterConnectorRequestTemplate:
    request_template_id: str = "p48_operator_local_runtime_connector_request_TEMPLATE"
    operator_id: str = "OPERATOR_ID_REQUIRED_AT_RUNTIME"
    approval_ticket_id: str = "APPROVAL_TICKET_ID_REQUIRED_AT_RUNTIME"
    p6_external_runtime_preflight_report_sha256: str = "P6_PREFLIGHT_REPORT_SHA256_REQUIRED"
    p5_action_time_boundary_sha256: str = "P5_ACTION_TIME_BOUNDARY_SHA256_REQUIRED"
    hot_path_preorder_risk_gate_id: str = "HOT_PATH_RISK_GATE_ID_REQUIRED_AT_RUNTIME"
    hot_path_preorder_risk_gate_sha256: str = "HOT_PATH_RISK_GATE_SHA256_REQUIRED_AT_RUNTIME"
    runtime_adapter_package_sha256: str = "EXTERNAL_RUNTIME_PACKAGE_SHA256_REQUIRED"
    secret_reference_id: str = "TESTNET_SECRET_REFERENCE_ID_REQUIRED"
    key_fingerprint_sha256: str = "KEY_FINGERPRINT_SHA256_REQUIRED"
    symbol: str = "BTCUSDT"
    environment: str = "testnet"
    max_order_count: int = 1
    requested_network_call_count: int = 1
    explicit_operator_runtime_network_allowance_required: bool = True
    execute_real_submit_now_default: bool = False
    generated_by_review_package: bool = True
    can_grant_runtime_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["connector_request_template_sha256"] = sha256_json(payload)
        return payload


def validate_local_runtime_adapter_connector_config(config: Mapping[str, Any] | LocalRuntimeAdapterConnectorConfig | None) -> dict[str, Any]:
    payload = config.to_dict() if isinstance(config, LocalRuntimeAdapterConnectorConfig) else dict(config or {})
    blockers: list[str] = []
    if not _nonempty(payload.get("connector_id")):
        blockers.append("P48_CONNECTOR_ID_MISSING")
    if payload.get("connector_version") != P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_VERSION:
        blockers.append("P48_CONNECTOR_VERSION_MISMATCH")
    if payload.get("review_package_default_no_submit") is not True:
        blockers.append("P48_REVIEW_PACKAGE_DEFAULT_NO_SUBMIT_NOT_TRUE")
    if payload.get("external_runtime_only") is not True:
        blockers.append("P48_CONNECTOR_NOT_EXTERNAL_RUNTIME_ONLY")
    if payload.get("real_adapter_code_included_in_review_package") is True:
        blockers.append("P48_REAL_ADAPTER_CODE_INCLUDED_IN_REVIEW_PACKAGE")
    if payload.get("local_runtime_connector_attached") is True:
        blockers.append("P48_LOCAL_RUNTIME_CONNECTOR_ATTACHED_IN_REVIEW_PACKAGE")
    if payload.get("can_submit_orders_by_default") is not False:
        blockers.append("P48_CONNECTOR_CAN_SUBMIT_BY_DEFAULT")
    if payload.get("network_calls_allowed_in_review_package") is not False:
        blockers.append("P48_NETWORK_CALLS_ALLOWED_IN_REVIEW_PACKAGE")
    if payload.get("environment") not in _ALLOWED_ENVIRONMENTS:
        blockers.append("P48_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") not in _ALLOWED_VENUES:
        blockers.append("P48_VENUE_NOT_TESTNET_SCOPED")
    if payload.get("symbol") not in _ALLOWED_SYMBOLS:
        blockers.append("P48_SYMBOL_NOT_BTCUSDT")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P48_MAX_ORDER_COUNT_NOT_ONE")
    if payload.get("request_signing_boundary") != "external_runtime_process_memory_only":
        blockers.append("P48_REQUEST_SIGNING_NOT_PROCESS_MEMORY_ONLY")
    if payload.get("secret_binding_mode") != "metadata_reference_only_in_review_package":
        blockers.append("P48_SECRET_BINDING_MODE_NOT_METADATA_ONLY")
    if payload.get("raw_secret_values_allowed_in_connector_config") is not False:
        blockers.append("P48_RAW_SECRET_VALUES_ALLOWED_IN_CONFIG")
    if payload.get("raw_exchange_payload_allowed_in_review_package") is not False:
        blockers.append("P48_RAW_EXCHANGE_PAYLOAD_ALLOWED_IN_REVIEW_PACKAGE")
    if not _is_sha256_hex(payload.get("key_fingerprint_sha256")):
        blockers.append("P48_KEY_FINGERPRINT_SHA256_INVALID")
    for key in (
        "p6_external_runtime_preflight_required",
        "p7_real_post_submit_evidence_required_after_submit",
        "p8_repeated_clean_sessions_required_before_live_canary",
        "operator_arming_phrase_required",
        "duplicate_submit_lock_required",
        "idempotency_key_required",
        "post_submit_relock_required",
        "redacted_evidence_export_required",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P48_{key.upper()}_NOT_TRUE")
    for key, value in payload.items():
        key_l = str(key).strip().lower()
        if key_l in _FORBIDDEN_SECRET_FIELDS and _nonempty(value):
            blockers.append(f"P48_FORBIDDEN_SECRET_FIELD_PRESENT:{key}")
    text_blob = " ".join(str(v).lower() for v in payload.values())
    for token in _FORBIDDEN_SCOPE_TOKENS:
        if token in text_blob:
            blockers.append(f"P48_FORBIDDEN_SCOPE_TOKEN_PRESENT:{token}")
    validation = {
        "connector_config_valid": not blockers,
        "connector_config_block_reasons": sorted(dict.fromkeys(blockers)),
        "connector_id": payload.get("connector_id"),
        "venue": payload.get("venue"),
        "environment": payload.get("environment"),
        "symbol": payload.get("symbol"),
        "review_package_default_no_submit": payload.get("review_package_default_no_submit") is True,
        "real_adapter_code_included_in_review_package": payload.get("real_adapter_code_included_in_review_package") is True,
        "local_runtime_connector_attached": payload.get("local_runtime_connector_attached") is True,
        "network_calls_allowed_in_review_package": payload.get("network_calls_allowed_in_review_package") is True,
    }
    validation["connector_config_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p6_preflight_source(p6_preflight: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(p6_preflight or {})
    blockers: list[str] = []
    if payload.get("artifact_type") != "p6_external_runtime_preflight_report":
        blockers.append("P48_P6_PREFLIGHT_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != "P6_EXTERNAL_RUNTIME_PREFLIGHT_READY_REVIEW_ONLY_NO_SUBMIT":
        blockers.append("P48_P6_PREFLIGHT_STATUS_NOT_READY_NO_SUBMIT")
    if payload.get("preflight_passed") is not True:
        blockers.append("P48_P6_PREFLIGHT_NOT_PASSED")
    if payload.get("review_package_default_no_submit") is not True:
        blockers.append("P48_P6_PREFLIGHT_NOT_REVIEW_PACKAGE_NO_SUBMIT")
    if payload.get("submit_requested") is not False:
        blockers.append("P48_P6_PREFLIGHT_SUBMIT_REQUESTED")
    if payload.get("runtime_network_call_allowed_by_operator") is not False:
        blockers.append("P48_P6_PREFLIGHT_RUNTIME_NETWORK_ALLOWED")
    for key in (
        "actual_order_submission_performed",
        "actual_testnet_order_submitted",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P48_P6_PREFLIGHT_{key.upper()}_NOT_FALSE")
    validation = {
        "p6_preflight_source_valid": not blockers,
        "p6_preflight_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_status": payload.get("status"),
        "source_sha256": payload.get("p6_external_runtime_preflight_report_sha256"),
    }
    validation["p6_preflight_source_validation_sha256"] = sha256_json(validation)
    return validation


def validate_connector_request_template(template: Mapping[str, Any] | LocalRuntimeAdapterConnectorRequestTemplate | None) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, LocalRuntimeAdapterConnectorRequestTemplate) else dict(template or {})
    blockers: list[str] = []
    if not _nonempty(payload.get("request_template_id")):
        blockers.append("P48_CONNECTOR_REQUEST_TEMPLATE_ID_MISSING")
    if payload.get("symbol") != "BTCUSDT":
        blockers.append("P48_CONNECTOR_REQUEST_SYMBOL_NOT_BTCUSDT")
    if payload.get("environment") != "testnet":
        blockers.append("P48_CONNECTOR_REQUEST_ENVIRONMENT_NOT_TESTNET")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P48_CONNECTOR_REQUEST_MAX_ORDER_COUNT_NOT_ONE")
    if int(payload.get("requested_network_call_count") or 0) != 1:
        blockers.append("P48_CONNECTOR_REQUEST_NETWORK_CALL_COUNT_NOT_ONE")
    if payload.get("explicit_operator_runtime_network_allowance_required") is not True:
        blockers.append("P48_CONNECTOR_REQUEST_OPERATOR_NETWORK_ALLOWANCE_NOT_REQUIRED")
    if payload.get("execute_real_submit_now_default") is not False:
        blockers.append("P48_CONNECTOR_REQUEST_EXECUTE_DEFAULT_NOT_FALSE")
    if payload.get("generated_by_review_package") is not True:
        blockers.append("P48_CONNECTOR_REQUEST_NOT_GENERATED_BY_REVIEW_PACKAGE")
    if payload.get("can_grant_runtime_authority") is not False:
        blockers.append("P48_CONNECTOR_REQUEST_CAN_GRANT_RUNTIME_AUTHORITY")
    for key, value in payload.items():
        key_l = str(key).strip().lower()
        if key_l in _FORBIDDEN_SECRET_FIELDS and _nonempty(value):
            blockers.append(f"P48_CONNECTOR_REQUEST_FORBIDDEN_SECRET_FIELD_PRESENT:{key}")
    validation = {
        "connector_request_template_valid": not blockers,
        "connector_request_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "request_template_id": payload.get("request_template_id"),
        "generated_by_review_package": payload.get("generated_by_review_package") is True,
        "can_grant_runtime_authority": payload.get("can_grant_runtime_authority") is True,
    }
    validation["connector_request_template_validation_sha256"] = sha256_json(validation)
    return validation


def build_p48_local_runtime_adapter_connector_report(
    *,
    cfg: AppConfig | None = None,
    connector_config: Mapping[str, Any] | LocalRuntimeAdapterConnectorConfig | None = None,
    request_template: Mapping[str, Any] | LocalRuntimeAdapterConnectorRequestTemplate | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = utc_now_canonical()
    p6_preflight = _read_latest_json(cfg, "p6_external_runtime_preflight_report.json")
    config_payload = connector_config.to_dict() if isinstance(connector_config, LocalRuntimeAdapterConnectorConfig) else dict(connector_config or LocalRuntimeAdapterConnectorConfig().to_dict())
    template_payload = request_template.to_dict() if isinstance(request_template, LocalRuntimeAdapterConnectorRequestTemplate) else dict(request_template or LocalRuntimeAdapterConnectorRequestTemplate().to_dict())
    config_validation = validate_local_runtime_adapter_connector_config(config_payload)
    p6_validation = validate_p6_preflight_source(p6_preflight)
    template_validation = validate_connector_request_template(template_payload)
    blockers = sorted(
        dict.fromkeys(
            list(config_validation["connector_config_block_reasons"])
            + list(p6_validation["p6_preflight_source_block_reasons"])
            + list(template_validation["connector_request_template_block_reasons"])
        )
    )
    status = STATUS_READY_REVIEW_ONLY_NO_SUBMIT if not blockers else STATUS_BLOCKED_FAIL_CLOSED
    report = {
        "artifact_type": "p48_local_runtime_adapter_connector_report",
        "p48_local_runtime_adapter_connector_version": P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_VERSION,
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "review_package_default_no_submit": True,
        "runtime_authority_source": False,
        "connector_design_only": True,
        "external_runtime_only": True,
        "real_adapter_code_included_in_review_package": False,
        "connector_can_be_attached_by_this_package": False,
        "actual_endpoint_call_still_requires_operator_local_runtime": True,
        "p6_source_preflight_validation": p6_validation,
        "connector_config": config_payload,
        "connector_config_validation": config_validation,
        "connector_request_template": template_payload,
        "connector_request_template_validation": template_validation,
        "next_required_chain": [
            "operator supplies separate local runtime package outside review ZIP",
            "operator binds testnet secret in process memory only",
            "fresh P6 preflight runs immediately before submit",
            "single BTCUSDT signed testnet submit evidence exported redacted",
            "P7 validates real post-submit evidence",
            "P8 accumulates repeated clean signed testnet sessions",
        ],
        "block_reasons": blockers,
        "created_at_utc": created_at_utc,
        **_execution_false_payload(),
    }
    unsafe = truthy_execution_flags(report)
    report["unsafe_truthy_execution_flags"] = unsafe
    if unsafe:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["fail_closed"] = True
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P48_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p48_local_runtime_adapter_connector_id"] = stable_id("p48_local_runtime_adapter_connector", report, 24)
    report["p48_local_runtime_adapter_connector_sha256"] = sha256_json(report)
    return report


def build_p48_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    cases: dict[str, dict[str, Any]] = {
        "mainnet_scope": {**LocalRuntimeAdapterConnectorConfig().to_dict(), "environment": "mainnet", "venue": "binance_mainnet"},
        "network_allowed_in_review_package": {**LocalRuntimeAdapterConnectorConfig().to_dict(), "network_calls_allowed_in_review_package": True},
        "real_adapter_included_in_review_package": {**LocalRuntimeAdapterConnectorConfig().to_dict(), "real_adapter_code_included_in_review_package": True},
        "connector_attached_in_review_package": {**LocalRuntimeAdapterConnectorConfig().to_dict(), "local_runtime_connector_attached": True},
        "secret_value_in_config": {**LocalRuntimeAdapterConnectorConfig().to_dict(), "api_secret": "SHOULD_NOT_APPEAR"},
        "bad_request_template_runtime_authority": LocalRuntimeAdapterConnectorRequestTemplate(can_grant_runtime_authority=True).to_dict(),
    }
    config_case_results: dict[str, dict[str, Any]] = {}
    template_case_results: dict[str, dict[str, Any]] = {}
    for name, payload in cases.items():
        if name.startswith("bad_request"):
            template_case_results[name] = validate_connector_request_template(payload)
        else:
            config_case_results[name] = validate_local_runtime_adapter_connector_config(payload)
    all_config_blocked = all(result["connector_config_valid"] is False for result in config_case_results.values())
    all_template_blocked = all(result["connector_request_template_valid"] is False for result in template_case_results.values())
    result = {
        "artifact_type": "p48_local_runtime_adapter_connector_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": bool(all_config_blocked and all_template_blocked),
        "config_fixture_results": config_case_results,
        "template_fixture_results": template_case_results,
        **_execution_false_payload(),
    }
    result["p48_negative_fixture_results_sha256"] = sha256_json(result)
    return result


def persist_p48_local_runtime_adapter_connector(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_p48_local_runtime_adapter_connector_report(cfg=cfg)
    negative = build_p48_negative_fixture_results(cfg=cfg)
    summary = {
        "artifact_type": "p48_local_runtime_adapter_connector_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": True,
        "review_package_default_no_submit": True,
        "external_runtime_only": True,
        "connector_design_only": True,
        "p6_source_preflight_valid": report["p6_source_preflight_validation"]["p6_preflight_source_valid"],
        "connector_config_valid": report["connector_config_validation"]["connector_config_valid"],
        "connector_request_template_valid": report["connector_request_template_validation"]["connector_request_template_valid"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        **_execution_false_payload(),
    }
    registry_record = {
        "artifact_type": "p48_local_runtime_adapter_connector_registry_record",
        "status": report["status"],
        "p48_local_runtime_adapter_connector_id": report["p48_local_runtime_adapter_connector_id"],
        "p48_local_runtime_adapter_connector_sha256": report["p48_local_runtime_adapter_connector_sha256"],
        "review_only": True,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
    }
    record = append_registry_record(
        registry_path(cfg, P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_REGISTRY_NAME),
        registry_record,
        registry_name=P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_REGISTRY_NAME,
        id_field="p48_local_runtime_adapter_connector_registry_record_id",
        hash_field="p48_local_runtime_adapter_connector_registry_record_sha256",
        id_prefix="p48_connector_registry_record",
    )
    summary["p48_local_runtime_adapter_connector_registry_record_sha256"] = record["p48_local_runtime_adapter_connector_registry_record_sha256"]
    summary["p48_local_runtime_adapter_connector_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p48_local_runtime_adapter_connector_report.json", report)
    atomic_write_json(latest / "p48_local_runtime_adapter_connector_TEMPLATE_NO_SUBMIT.json", report["connector_config"])
    atomic_write_json(latest / "p48_operator_local_runtime_connector_request_TEMPLATE.json", report["connector_request_template"])
    atomic_write_json(latest / "p48_local_runtime_adapter_connector_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p48_local_runtime_adapter_connector_registry_record.json", record)
    atomic_write_json(latest / "p48_local_runtime_adapter_connector_summary.json", summary)
    return report
