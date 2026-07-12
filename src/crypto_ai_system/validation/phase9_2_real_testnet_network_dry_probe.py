from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_2_real_testnet_endpoint_adapter_preflight import _hash
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool
from crypto_ai_system.execution.phase9_2_single_testnet_runtime_submit_wrapper import RUNTIME_FALSE_FLAGS

PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_VERSION = "phase9_2_real_testnet_network_dry_probe_v1"
PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_REGISTRY_NAME = "phase9_2_real_testnet_network_dry_probe_registry"
STATUS_RECORDED = "PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_RECORDED_NO_ORDER_SUBMIT_REVIEW_ONLY"
STATUS_BLOCKED = "PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_BLOCKED_FAIL_CLOSED"
SOURCE_PREFLIGHT_FILE = "phase9_2_real_testnet_endpoint_adapter_preflight_report.json"

NETWORK_DRY_PROBE_FALSE_FLAGS = sorted(set(RUNTIME_FALSE_FLAGS + [
    "real_testnet_submit_may_begin",
    "real_testnet_endpoint_adapter_attached",
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
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "live_canary_preparation_may_begin",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
]))

REQUIRED_PROBE_FIELDS = [
    "exchange",
    "environment",
    "probe_mode",
    "endpoint_base_url_config_ref",
    "allowed_public_metadata_endpoint_refs",
    "forbidden_private_or_order_endpoint_refs",
    "timeout_ms",
    "max_attempts",
    "requires_signature",
    "requires_api_key_value",
    "requires_api_secret_value",
    "order_submit_allowed",
    "cancel_allowed",
    "status_polling_allowed",
]

ALLOWED_PUBLIC_ENDPOINT_REFS = [
    "testnet_exchange_time_endpoint_ref_only",
    "testnet_exchange_info_endpoint_ref_only",
    "testnet_symbol_info_endpoint_ref_only",
]

FORBIDDEN_ENDPOINT_REFS = [
    "testnet_order_endpoint_ref_forbidden_in_dry_probe",
    "testnet_cancel_endpoint_ref_forbidden_in_dry_probe",
    "testnet_order_status_endpoint_ref_forbidden_in_dry_probe",
    "testnet_account_balance_endpoint_ref_forbidden_in_dry_probe",
    "testnet_position_endpoint_ref_forbidden_in_dry_probe",
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
    return {field: False for field in NETWORK_DRY_PROBE_FALSE_FLAGS}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return sorted(field for field in NETWORK_DRY_PROBE_FALSE_FLAGS if _safe_bool(data.get(field)))


def _source_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": "phase9_2_real_testnet_endpoint_adapter_preflight_report",
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _hash(data),
        "preflight_ready_for_manual_review_only": data.get("preflight_ready_for_manual_review_only"),
        "real_testnet_submit_may_begin": data.get("real_testnet_submit_may_begin"),
        "actual_order_submission_performed": data.get("actual_order_submission_performed"),
        "order_endpoint_called": data.get("order_endpoint_called"),
    }


def _source_ready(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    data = dict(payload or {})
    blockers: list[str] = []
    if not data:
        return False, ["PHASE9_2_NETWORK_DRY_PROBE_SOURCE_PREFLIGHT_REPORT_MISSING"]
    if data.get("blocked") is True or data.get("fail_closed") is True:
        blockers.append("PHASE9_2_NETWORK_DRY_PROBE_SOURCE_PREFLIGHT_BLOCKED")
    if data.get("preflight_ready_for_manual_review_only") is not True:
        blockers.append("PHASE9_2_NETWORK_DRY_PROBE_REQUIRES_PREFLIGHT_READY")
    if data.get("real_testnet_submit_may_begin") is not False:
        blockers.append("PHASE9_2_NETWORK_DRY_PROBE_SOURCE_SUBMIT_FLAG_MUST_REMAIN_FALSE")
    for field in [
        "actual_order_submission_performed",
        "real_exchange_endpoint_call_performed",
        "order_endpoint_called",
        "order_status_endpoint_called",
        "cancel_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
    ]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_NETWORK_DRY_PROBE_UNSAFE_SOURCE_FLAG:{field}")
    unsafe = _unsafe_true_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_NETWORK_DRY_PROBE_SOURCE_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    return not blockers, blockers


def build_network_dry_probe_template(source_preflight: Mapping[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    template_id = stable_id("phase9_2_real_testnet_network_dry_probe_template", {
        "source_preflight_sha256": _hash(source_preflight),
        "version": PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_VERSION,
    }, 24)
    payload = {
        "artifact_type": "phase9_2_real_testnet_network_dry_probe_template_no_order_submit_review_only",
        "phase9_2_real_testnet_network_dry_probe_template_id": template_id,
        "phase9_2_real_testnet_network_dry_probe_version": PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_VERSION,
        "review_only": True,
        "no_order_submit": True,
        "network_dry_probe_only": True,
        "source_preflight_report_sha256": _hash(source_preflight),
        "network_probe_execution_default": "disabled_until_operator_runs_no_order_dry_probe_command",
        "probe_plan": {
            "exchange": "CONFIGURED_TESTNET_EXCHANGE_REVIEW_ONLY",
            "environment": "testnet",
            "probe_mode": "public_metadata_read_only_no_order_submit",
            "endpoint_base_url_config_ref": "CAS_TESTNET_ENDPOINT_BASE_URL_REF_ONLY",
            "allowed_public_metadata_endpoint_refs": ALLOWED_PUBLIC_ENDPOINT_REFS,
            "forbidden_private_or_order_endpoint_refs": FORBIDDEN_ENDPOINT_REFS,
            "timeout_ms": 3000,
            "max_attempts": 1,
            "requires_signature": False,
            "requires_api_key_value": False,
            "requires_api_secret_value": False,
            "order_submit_allowed": False,
            "cancel_allowed": False,
            "status_polling_allowed": False,
        },
        "required_probe_fields": REQUIRED_PROBE_FIELDS,
        "allowed_probe_result_fields": [
            "dns_or_url_config_resolved",
            "exchange_time_reachable",
            "exchange_info_reachable",
            "symbol_info_reachable",
            "latency_ms",
            "http_status_code",
            "api_error_code",
            "rate_limit_observed",
        ],
        "forbidden_probe_result_fields": [
            "order_id",
            "client_order_id",
            "signature",
            "api_key",
            "api_secret",
            "balance",
            "position",
            "open_orders",
        ],
        "public_metadata_network_probe_performed": False,
        "network_dry_probe_result_intake_ready": True,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_real_testnet_network_dry_probe_template_sha256"] = sha256_json(payload)
    return payload


def validate_network_dry_probe_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    plan = data.get("probe_plan")
    plan = dict(plan) if isinstance(plan, Mapping) else {}
    unsafe = _unsafe_true_fields(data)
    secret_like = _find_secret_like_values(data)
    errors: list[str] = []
    if data.get("review_only") is not True:
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_REQUIRES_REVIEW_ONLY_TRUE")
    if data.get("no_order_submit") is not True:
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_REQUIRES_NO_ORDER_SUBMIT_TRUE")
    if data.get("network_dry_probe_only") is not True:
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_REQUIRES_DRY_PROBE_ONLY_TRUE")
    missing = [field for field in REQUIRED_PROBE_FIELDS if field not in plan or plan.get(field) in (None, "", [])]
    if missing:
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_MISSING_PROBE_FIELDS:" + ",".join(missing))
    if str(plan.get("environment", "")).lower() != "testnet":
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_ENVIRONMENT_MUST_BE_TESTNET")
    if any(term in str(plan.get("environment", "")).lower() for term in ["live", "mainnet"]):
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_LIVE_OR_MAINNET_ENV_FORBIDDEN")
    for field in ["requires_signature", "requires_api_key_value", "requires_api_secret_value", "order_submit_allowed", "cancel_allowed", "status_polling_allowed"]:
        if plan.get(field) is not False:
            errors.append(f"PHASE9_2_NETWORK_DRY_PROBE_UNSAFE_PLAN_PERMISSION:{field}")
    allowed_refs = plan.get("allowed_public_metadata_endpoint_refs")
    allowed_text = " ".join(str(x).lower() for x in allowed_refs) if isinstance(allowed_refs, list) else str(allowed_refs).lower()
    for forbidden in ["order", "cancel", "account", "balance", "position", "private", "trade"]:
        if forbidden in allowed_text:
            errors.append("PHASE9_2_NETWORK_DRY_PROBE_ALLOWED_REFS_CONTAIN_FORBIDDEN_ENDPOINT:" + forbidden)
    if data.get("public_metadata_network_probe_performed") is not False:
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_TEMPLATE_MUST_NOT_MARK_NETWORK_PROBE_PERFORMED")
    if unsafe:
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    if secret_like:
        errors.append("PHASE9_2_NETWORK_DRY_PROBE_SECRET_LIKE_VALUES_PRESENT")
    return {
        "artifact_type": "phase9_2_real_testnet_network_dry_probe_validation_report",
        "phase9_2_real_testnet_network_dry_probe_version": PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_VERSION,
        "review_only": True,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "network_dry_probe_payload_valid": not errors,
        "probe_plan_complete": not missing if 'missing' in locals() else False,
        "missing_probe_fields": missing if 'missing' in locals() else REQUIRED_PROBE_FIELDS,
        "unsafe_true_fields": unsafe,
        "secret_like_values_detected": bool(secret_like),
        "block_reasons": errors,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }


def build_negative_fixture_results() -> dict[str, Any]:
    base = build_network_dry_probe_template({}, created_at_utc="2026-01-01T00:00:00Z")
    fixtures = {
        "order_endpoint_in_allowed_refs": {**base, "probe_plan": {**base["probe_plan"], "allowed_public_metadata_endpoint_refs": ["testnet_order_endpoint"]}},
        "signature_required_true": {**base, "probe_plan": {**base["probe_plan"], "requires_signature": True}},
        "api_secret_required_true": {**base, "probe_plan": {**base["probe_plan"], "requires_api_secret_value": True}},
        "order_submit_allowed_true": {**base, "probe_plan": {**base["probe_plan"], "order_submit_allowed": True}},
        "network_probe_performed_true": {**base, "public_metadata_network_probe_performed": True},
        "actual_order_submission_true": {**base, "actual_order_submission_performed": True},
        "live_environment": {**base, "probe_plan": {**base["probe_plan"], "environment": "live"}},
        "secret_like_value": {**base, "api_secret": "SECRET_VALUE_SHOULD_NOT_BE_HERE"},
    }
    results: dict[str, Any] = {}
    for name, payload in fixtures.items():
        validation = validate_network_dry_probe_payload(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    output = {
        "artifact_type": "phase9_2_real_testnet_network_dry_probe_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_real_testnet_network_dry_probe_negative_fixture_results_sha256"] = sha256_json(output)
    return output


def build_phase9_2_real_testnet_network_dry_probe_report(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    source = _read_latest_json(cfg, SOURCE_PREFLIGHT_FILE)
    source_ready, source_blockers = _source_ready(source)
    template = build_network_dry_probe_template(source, created_at_utc=created_at_utc) if source_ready else {}
    validation = validate_network_dry_probe_payload(template) if template else {}
    blockers = list(source_blockers) + (validation.get("block_reasons", []) if validation else [])
    report_id = stable_id("phase9_2_real_testnet_network_dry_probe", {
        "source": _source_summary(source),
        "template_hash": template.get("phase9_2_real_testnet_network_dry_probe_template_sha256") if template else None,
    }, 24)
    report = {
        "artifact_type": "phase9_2_real_testnet_network_dry_probe_report",
        "phase9_2_real_testnet_network_dry_probe_id": report_id,
        "phase9_2_real_testnet_network_dry_probe_version": PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_VERSION,
        "status": STATUS_BLOCKED if blockers else STATUS_RECORDED,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "no_order_submit": True,
        "network_dry_probe_only": True,
        "source_preflight_summary": _source_summary(source),
        "source_blockers": source_blockers,
        "network_dry_probe_template_created": bool(template),
        "network_dry_probe_payload_valid": bool(validation and validation.get("network_dry_probe_payload_valid")),
        "network_dry_probe_ready_for_operator_no_order_command": bool(template and validation and not blockers),
        "public_metadata_network_probe_performed": False,
        "real_testnet_submit_may_begin": False,
        "real_testnet_endpoint_adapter_attached": False,
        "order_endpoint_calls_allowed": False,
        "signature_creation_allowed": False,
        "http_transmission_allowed_for_order": False,
        "block_reasons": blockers,
        "recommended_next_action": "operator_may_run_public_metadata_network_dry_probe_no_order_submit_then_record_redacted_results_before_any_runtime_submit",
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_real_testnet_network_dry_probe_report_sha256"] = sha256_json(report)
    return report, template


def persist_phase9_2_real_testnet_network_dry_probe(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, template = build_phase9_2_real_testnet_network_dry_probe_report(cfg=cfg)
    validation = validate_network_dry_probe_payload(template) if template else validate_network_dry_probe_payload({})
    negative = build_negative_fixture_results()
    files: dict[str, Mapping[str, Any]] = {
        "phase9_2_real_testnet_network_dry_probe_report.json": report,
        "phase9_2_real_testnet_network_dry_probe_validation_report.json": validation,
        "phase9_2_real_testnet_network_dry_probe_negative_fixture_results.json": negative,
    }
    if template:
        files["phase9_2_real_testnet_network_dry_probe_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json"] = template
    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)
    handoff = "\n".join([
        "# Phase 9.2 Real Testnet Network Dry Probe / No Order Submit",
        "",
        "This packet prepares a public-metadata-only testnet network dry probe.",
        "It does not call order, cancel, order-status, account, balance, or position endpoints.",
        "It does not create signatures, read API secrets, send signed requests, or submit orders.",
        "Only public metadata endpoint reachability may be checked by a later explicit no-order operator command.",
    ])
    (latest / "PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")
    record = append_registry_record(
        registry_path(cfg, PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_real_testnet_network_dry_probe_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_order_submit": True,
            "sha256": report["phase9_2_real_testnet_network_dry_probe_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_REAL_TESTNET_NETWORK_DRY_PROBE_REGISTRY_NAME,
        id_field="phase9_2_real_testnet_network_dry_probe_registry_id",
        hash_field="phase9_2_real_testnet_network_dry_probe_registry_record_sha256",
        id_prefix="phase9_2_real_testnet_network_dry_probe_registry",
    )
    atomic_write_json(latest / "phase9_2_real_testnet_network_dry_probe_registry_record.json", record)
    return report
