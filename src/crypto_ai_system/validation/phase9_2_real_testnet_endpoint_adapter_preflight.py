from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.phase9_2_single_testnet_runtime_submit_wrapper import RUNTIME_FALSE_FLAGS
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool

PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_VERSION = "phase9_2_real_testnet_endpoint_adapter_preflight_v1"
PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_REGISTRY_NAME = "phase9_2_real_testnet_endpoint_adapter_preflight_registry"
STATUS_PREFLIGHT_RECORDED = "PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_RECORDED_NO_SUBMIT_REVIEW_ONLY"
STATUS_PREFLIGHT_BLOCKED = "PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_BLOCKED_FAIL_CLOSED"

SOURCE_MOCK_FLOW_FILE = "phase9_2_mock_submit_evidence_flow_report.json"

PREFLIGHT_FALSE_FLAGS = sorted(set(RUNTIME_FALSE_FLAGS + [
    "real_testnet_endpoint_preflight_performed_against_network",
    "real_testnet_order_endpoint_reachable_checked",
    "real_testnet_order_endpoint_called",
    "real_exchange_endpoint_call_performed",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "real_order_submit_attempted",
    "real_order_id_created",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "live_canary_preparation_may_begin",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
]))

REQUIRED_INTERFACE_FIELDS = [
    "exchange",
    "environment",
    "adapter_mode",
    "endpoint_base_url_config_ref",
    "order_endpoint_path_ref",
    "status_endpoint_path_ref",
    "cancel_endpoint_path_ref",
    "timestamp_source",
    "recv_window_ms",
    "symbol",
    "symbol_rules_source_ref",
    "min_notional_source_ref",
    "price_tick_source_ref",
    "quantity_step_source_ref",
    "key_ref",
    "key_fingerprint_sha256",
    "permission_scope_ref",
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
    return {field: False for field in PREFLIGHT_FALSE_FLAGS}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return sorted(field for field in PREFLIGHT_FALSE_FLAGS if _safe_bool(data.get(field)))


def _hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_2_mock_submit_evidence_flow_report_sha256",
        "phase9_2_real_testnet_endpoint_adapter_preflight_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": "phase9_2_mock_submit_evidence_flow_report",
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _hash(data),
        "mock_flow_ready_for_review_only_evidence_intake": data.get("mock_flow_ready_for_review_only_evidence_intake"),
        "actual_order_submission_performed": data.get("actual_order_submission_performed"),
        "real_exchange_endpoint_call_performed": data.get("real_exchange_endpoint_call_performed"),
    }


def _source_ready(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    data = dict(payload or {})
    blockers: list[str] = []
    if not data:
        blockers.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_SOURCE_MOCK_FLOW_REPORT_MISSING")
        return False, blockers
    if data.get("blocked") is True or data.get("fail_closed") is True:
        blockers.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_SOURCE_MOCK_FLOW_BLOCKED")
    if data.get("mock_flow_ready_for_review_only_evidence_intake") is not True:
        blockers.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_REQUIRES_MOCK_EVIDENCE_FLOW_READY")
    for field in ["actual_order_submission_performed", "real_exchange_endpoint_call_performed", "order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_REAL_TESTNET_PREFLIGHT_UNSAFE_SOURCE_FLAG:{field}")
    unsafe = _unsafe_true_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_SOURCE_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    return not blockers, blockers


def build_preflight_template(source_mock_flow: Mapping[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    template_id = stable_id("phase9_2_real_testnet_endpoint_adapter_preflight_template", {
        "source_mock_flow_sha256": _hash(source_mock_flow),
        "version": PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_VERSION,
    }, 24)
    payload = {
        "artifact_type": "phase9_2_real_testnet_endpoint_adapter_preflight_template_no_submit_review_only",
        "phase9_2_real_testnet_endpoint_adapter_preflight_template_id": template_id,
        "phase9_2_real_testnet_endpoint_adapter_preflight_version": PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_VERSION,
        "review_only": True,
        "no_submit": True,
        "preflight_only": True,
        "network_calls_allowed": False,
        "order_endpoint_calls_allowed": False,
        "signature_creation_allowed": False,
        "http_transmission_allowed": False,
        "source_mock_flow_report_sha256": _hash(source_mock_flow),
        "adapter_interface": {
            "exchange": "CONFIGURED_TESTNET_EXCHANGE_REVIEW_ONLY",
            "environment": "testnet",
            "adapter_mode": "real_testnet_endpoint_adapter_preflight_no_submit",
            "endpoint_base_url_config_ref": "CAS_TESTNET_ENDPOINT_BASE_URL_REF_ONLY",
            "order_endpoint_path_ref": "CAS_TESTNET_ORDER_ENDPOINT_PATH_REF_ONLY",
            "status_endpoint_path_ref": "CAS_TESTNET_STATUS_ENDPOINT_PATH_REF_ONLY",
            "cancel_endpoint_path_ref": "CAS_TESTNET_CANCEL_ENDPOINT_PATH_REF_ONLY",
            "timestamp_source": "system_clock_or_exchange_time_ref_no_network_call_in_this_preflight",
            "recv_window_ms": 5000,
            "symbol": "BTCUSDT_TESTNET_REVIEW_ONLY",
            "symbol_rules_source_ref": "testnet_symbol_rules_metadata_ref_only",
            "min_notional_source_ref": "testnet_min_notional_metadata_ref_only",
            "price_tick_source_ref": "testnet_price_tick_metadata_ref_only",
            "quantity_step_source_ref": "testnet_quantity_step_metadata_ref_only",
            "key_ref": "TESTNET_KEY_REF_ONLY_NO_VALUE",
            "key_fingerprint_sha256": "" + ("c" * 64),
            "permission_scope_ref": "testnet_trade_scope_metadata_ref_only_no_withdrawal_no_transfer_no_admin",
        },
        "required_interface_fields": REQUIRED_INTERFACE_FIELDS,
        "required_runtime_guards_before_any_future_submit": [
            "explicit_runtime_submit_approval_text",
            "fresh_endpoint_time_preorder_risk_refresh",
            "duplicate_submit_lock",
            "testnet_only_endpoint_policy",
            "metadata_only_key_fingerprint_match",
            "post_submit_relock",
        ],
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_real_testnet_endpoint_adapter_preflight_template_sha256"] = sha256_json(payload)
    return payload


def validate_preflight_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    interface = data.get("adapter_interface")
    interface = dict(interface) if isinstance(interface, Mapping) else {}
    unsafe = _unsafe_true_fields(data)
    secret_like = _find_secret_like_values(data)
    errors: list[str] = []
    if data.get("review_only") is not True:
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_REQUIRES_REVIEW_ONLY_TRUE")
    if data.get("no_submit") is not True:
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_REQUIRES_NO_SUBMIT_TRUE")
    if data.get("preflight_only") is not True:
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_REQUIRES_PREFLIGHT_ONLY_TRUE")
    for field in ["network_calls_allowed", "order_endpoint_calls_allowed", "signature_creation_allowed", "http_transmission_allowed"]:
        if data.get(field) is not False:
            errors.append(f"PHASE9_2_REAL_TESTNET_PREFLIGHT_UNSAFE_PERMISSION:{field}")
    missing = [field for field in REQUIRED_INTERFACE_FIELDS if not interface.get(field)]
    if missing:
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_MISSING_INTERFACE_FIELDS:" + ",".join(missing))
    if interface.get("environment") != "testnet":
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_ENVIRONMENT_MUST_BE_TESTNET")
    if "live" in str(interface.get("environment", "")).lower() or "mainnet" in str(interface.get("environment", "")).lower():
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_LIVE_OR_MAINNET_ENV_FORBIDDEN")
    fp = str(interface.get("key_fingerprint_sha256") or "")
    if len(fp) != 64 or any(ch not in "0123456789abcdef" for ch in fp.lower()):
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_KEY_FINGERPRINT_INVALID_OR_PLACEHOLDER")
    if unsafe:
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    if secret_like:
        errors.append("PHASE9_2_REAL_TESTNET_PREFLIGHT_SECRET_LIKE_VALUES_PRESENT")
    return {
        "artifact_type": "phase9_2_real_testnet_endpoint_adapter_preflight_validation_report",
        "phase9_2_real_testnet_endpoint_adapter_preflight_version": PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_VERSION,
        "review_only": True,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "preflight_payload_valid": not errors,
        "adapter_interface_complete": not missing if 'missing' in locals() else False,
        "missing_interface_fields": missing if 'missing' in locals() else REQUIRED_INTERFACE_FIELDS,
        "unsafe_true_fields": unsafe,
        "secret_like_values_detected": bool(secret_like),
        "block_reasons": errors,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }


def build_negative_fixture_results() -> dict[str, Any]:
    base = build_preflight_template({}, created_at_utc="2026-01-01T00:00:00Z")
    fixtures = {
        "order_endpoint_call_allowed_true": {**base, "order_endpoint_calls_allowed": True},
        "network_calls_allowed_true": {**base, "network_calls_allowed": True},
        "signature_creation_allowed_true": {**base, "signature_creation_allowed": True},
        "actual_order_submission_true": {**base, "actual_order_submission_performed": True},
        "live_environment": {**base, "adapter_interface": {**base["adapter_interface"], "environment": "live"}},
        "secret_like_value": {**base, "api_secret": "SECRET_VALUE_SHOULD_NOT_BE_HERE"},
    }
    results: dict[str, Any] = {}
    for name, payload in fixtures.items():
        validation = validate_preflight_payload(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    output = {
        "artifact_type": "phase9_2_real_testnet_endpoint_adapter_preflight_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_real_testnet_endpoint_adapter_preflight_negative_fixture_results_sha256"] = sha256_json(output)
    return output


def build_phase9_2_real_testnet_endpoint_adapter_preflight_report(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    source = _read_latest_json(cfg, SOURCE_MOCK_FLOW_FILE)
    source_ready, source_blockers = _source_ready(source)
    template = build_preflight_template(source, created_at_utc=created_at_utc) if source_ready else {}
    validation = validate_preflight_payload(template) if template else {}
    blockers = list(source_blockers) + (validation.get("block_reasons", []) if validation else [])
    report_id = stable_id("phase9_2_real_testnet_endpoint_adapter_preflight", {
        "source": _source_summary(source),
        "template_hash": template.get("phase9_2_real_testnet_endpoint_adapter_preflight_template_sha256") if template else None,
    }, 24)
    report = {
        "artifact_type": "phase9_2_real_testnet_endpoint_adapter_preflight_report",
        "phase9_2_real_testnet_endpoint_adapter_preflight_id": report_id,
        "phase9_2_real_testnet_endpoint_adapter_preflight_version": PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_VERSION,
        "status": STATUS_PREFLIGHT_BLOCKED if blockers else STATUS_PREFLIGHT_RECORDED,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "no_submit": True,
        "preflight_only": True,
        "source_mock_flow_summary": _source_summary(source),
        "source_blockers": source_blockers,
        "adapter_interface_template_created": bool(template),
        "adapter_preflight_payload_valid": bool(validation and validation.get("preflight_payload_valid")),
        "preflight_ready_for_manual_review_only": bool(template and validation and not blockers),
        "real_testnet_submit_may_begin": False,
        "real_testnet_endpoint_adapter_attached": False,
        "real_testnet_endpoint_preflight_performed_against_network": False,
        "block_reasons": blockers,
        "recommended_next_action": "review_adapter_preflight_metadata_then_add_explicit_real_testnet_network_dry_probe_separately_before_any_submit",
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_real_testnet_endpoint_adapter_preflight_report_sha256"] = sha256_json(report)
    return report, template


def persist_phase9_2_real_testnet_endpoint_adapter_preflight(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, template = build_phase9_2_real_testnet_endpoint_adapter_preflight_report(cfg=cfg)
    validation = validate_preflight_payload(template) if template else validate_preflight_payload({})
    negative = build_negative_fixture_results()

    files: dict[str, Mapping[str, Any]] = {
        "phase9_2_real_testnet_endpoint_adapter_preflight_report.json": report,
        "phase9_2_real_testnet_endpoint_adapter_preflight_validation_report.json": validation,
        "phase9_2_real_testnet_endpoint_adapter_preflight_negative_fixture_results.json": negative,
    }
    if template:
        files["phase9_2_real_testnet_endpoint_adapter_PREFLIGHT_TEMPLATE_NO_SUBMIT_REVIEW_ONLY.json"] = template

    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)

    handoff = "\n".join([
        "# Phase 9.2 Real Testnet Endpoint Adapter Preflight / No Submit",
        "",
        "This packet defines the metadata-only interface required before attaching a real testnet endpoint adapter.",
        "It does not perform network reachability checks, create signatures, send HTTP requests, or submit orders.",
        "Endpoint paths, symbol rules, min notional, recvWindow, key references, and permission scope are recorded as review-only references.",
        "A later separately approved network dry probe may validate reachability, but order submission remains blocked until a one-order-only runtime submit approval is explicit.",
    ])
    (latest / "PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_HANDOFF_NO_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")

    record = append_registry_record(
        registry_path(cfg, PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_real_testnet_endpoint_adapter_preflight_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_submit": True,
            "sha256": report["phase9_2_real_testnet_endpoint_adapter_preflight_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_REAL_TESTNET_ENDPOINT_ADAPTER_PREFLIGHT_REGISTRY_NAME,
        id_field="phase9_2_real_testnet_endpoint_adapter_preflight_registry_id",
        hash_field="phase9_2_real_testnet_endpoint_adapter_preflight_registry_record_sha256",
        id_prefix="phase9_2_real_testnet_endpoint_adapter_preflight_registry",
    )
    atomic_write_json(latest / "phase9_2_real_testnet_endpoint_adapter_preflight_registry_record.json", record)
    return report
