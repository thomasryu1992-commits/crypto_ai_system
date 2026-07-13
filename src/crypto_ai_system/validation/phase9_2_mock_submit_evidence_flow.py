from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.phase9_2_single_testnet_runtime_submit_wrapper import (
    POST_ACTION_RELOCK_FLAGS,
    RUNTIME_FALSE_FLAGS,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool

PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_VERSION = "phase9_2_mock_submit_evidence_flow_v1"
PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_REGISTRY_NAME = "phase9_2_mock_submit_evidence_flow_registry"
STATUS_MOCK_SUBMIT_EVIDENCE_FLOW_RECORDED = "PHASE9_2_MOCK_SUBMIT_TO_EVIDENCE_FLOW_RECORDED_REVIEW_ONLY"
STATUS_MOCK_SUBMIT_EVIDENCE_FLOW_BLOCKED = "PHASE9_2_MOCK_SUBMIT_TO_EVIDENCE_FLOW_BLOCKED_FAIL_CLOSED"

SOURCE_FILE = "phase9_2_single_testnet_runtime_submit_wrapper_report.json"

FLOW_FALSE_FLAGS = sorted(set(RUNTIME_FALSE_FLAGS + [
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "reconciliation_started",
    "phase10_session_validation_started",
    "live_canary_preparation_may_begin",
    "real_exchange_endpoint_call_performed",
    "real_order_id_created",
    "real_order_submit_attempted",
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
    return {field: False for field in FLOW_FALSE_FLAGS}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return sorted(field for field in FLOW_FALSE_FLAGS if _safe_bool(data.get(field)))


def _hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_2_single_testnet_runtime_submit_wrapper_report_sha256",
        "phase9_2_mock_submit_evidence_flow_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": "phase9_2_single_testnet_runtime_submit_wrapper_report",
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _hash(data),
        "mock_order_submission_performed": data.get("mock_order_submission_performed"),
        "actual_order_submission_performed": data.get("actual_order_submission_performed"),
        "real_exchange_endpoint_call_performed": data.get("real_exchange_endpoint_call_performed"),
    }


def _source_ready(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    data = dict(payload or {})
    blockers: list[str] = []
    if not data:
        blockers.append("PHASE9_2_MOCK_EVIDENCE_FLOW_SOURCE_WRAPPER_REPORT_MISSING")
        return False, blockers
    unsafe = _unsafe_true_fields(data)
    if unsafe:
        blockers.append("PHASE9_2_MOCK_EVIDENCE_FLOW_SOURCE_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    if data.get("mock_order_submission_performed") is not True:
        blockers.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REQUIRES_MOCK_SUBMIT_PERFORMED_TRUE")
    if data.get("actual_order_submission_performed") is not False:
        blockers.append("PHASE9_2_MOCK_EVIDENCE_FLOW_ACTUAL_SUBMIT_MUST_REMAIN_FALSE")
    if data.get("real_exchange_endpoint_call_performed") is not False:
        blockers.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REAL_ENDPOINT_CALL_MUST_REMAIN_FALSE")
    response = data.get("mock_exchange_response_redacted")
    if not isinstance(response, Mapping) or response.get("mock_response") is not True:
        blockers.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REDACTED_MOCK_RESPONSE_MISSING")
    for field in ["order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_MOCK_EVIDENCE_FLOW_UNSAFE_SOURCE_FLAG:{field}")
    return not blockers, blockers


def _mock_response(wrapper_report: Mapping[str, Any]) -> dict[str, Any]:
    response = dict(wrapper_report.get("mock_exchange_response_redacted") or {})
    return response


def build_phase9_2_mock_execution_evidence(wrapper_report: Mapping[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    response = _mock_response(wrapper_report)
    evidence_id = stable_id("phase9_2_mock_execution_evidence", {
        "wrapper_hash": _hash(wrapper_report),
        "client_order_id": response.get("client_order_id"),
        "exchange_order_id": response.get("exchange_order_id"),
    }, 24)
    payload = {
        "artifact_type": "phase9_2_mock_execution_evidence_review_only",
        "phase9_2_mock_execution_evidence_id": evidence_id,
        "phase9_2_mock_submit_evidence_flow_version": PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_VERSION,
        "review_only": True,
        "mock_evidence_only": True,
        "usable_for_real_phase9_3_polling": False,
        "usable_for_real_phase9_4_reconciliation": False,
        "source_wrapper_report_sha256": _hash(wrapper_report),
        "phase": "9.2_mock",
        "exchange": response.get("exchange", "mock_testnet"),
        "symbol": response.get("symbol") or wrapper_report.get("symbol"),
        "side": response.get("side") or wrapper_report.get("side"),
        "order_type": response.get("order_type") or wrapper_report.get("order_type"),
        "quantity": response.get("quantity") or wrapper_report.get("quantity"),
        "max_notional": wrapper_report.get("max_notional"),
        "testnet_only": True,
        "max_order_count": 1,
        "idempotency_key": response.get("idempotency_key") or wrapper_report.get("idempotency_key"),
        "client_order_id": response.get("client_order_id"),
        "exchange_order_id": response.get("exchange_order_id"),
        "exchange_order_status": response.get("status", "MOCK_ACCEPTED"),
        "mock_order_submission_performed": True,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "private_key_logged": False,
        "passphrase_logged": False,
        **_disabled_payload(),
        **POST_ACTION_RELOCK_FLAGS,
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_mock_execution_evidence_sha256"] = sha256_json(payload)
    return payload


def build_phase9_3_mock_status_input(mock_execution: Mapping[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    payload = {
        "artifact_type": "phase9_3_mock_status_input_from_phase9_2_mock_submit_review_only",
        "phase9_2_mock_submit_evidence_flow_version": PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_VERSION,
        "review_only": True,
        "mock_evidence_only": True,
        "real_status_polling_allowed": False,
        "phase9_3_status_polling_may_begin": False,
        "source_phase9_2_mock_execution_evidence_sha256": mock_execution.get("phase9_2_mock_execution_evidence_sha256"),
        "exchange_order_id": mock_execution.get("exchange_order_id"),
        "client_order_id": mock_execution.get("client_order_id"),
        "idempotency_key": mock_execution.get("idempotency_key"),
        "status_polling_scope": "mock_single_testnet_order_only_no_endpoint_calls",
        "status_polling_events": [
            {
                "event_type": "mock_status_snapshot",
                "status": mock_execution.get("exchange_order_status", "MOCK_ACCEPTED"),
                "event_timestamp_utc": created_at_utc,
                "endpoint_called": False,
            }
        ],
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_3_mock_status_input_sha256"] = sha256_json(payload)
    return payload


def build_phase9_4_mock_reconciliation_input(
    mock_execution: Mapping[str, Any],
    mock_status_input: Mapping[str, Any],
    *,
    created_at_utc: str,
) -> dict[str, Any]:
    payload = {
        "artifact_type": "phase9_4_mock_reconciliation_input_from_phase9_2_mock_submit_review_only",
        "phase9_2_mock_submit_evidence_flow_version": PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_VERSION,
        "review_only": True,
        "mock_evidence_only": True,
        "real_reconciliation_allowed": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "source_phase9_2_mock_execution_evidence_sha256": mock_execution.get("phase9_2_mock_execution_evidence_sha256"),
        "source_phase9_3_mock_status_input_sha256": mock_status_input.get("phase9_3_mock_status_input_sha256"),
        "exchange_order_id": mock_execution.get("exchange_order_id"),
        "client_order_id": mock_execution.get("client_order_id"),
        "exchange_order_status": mock_execution.get("exchange_order_status"),
        "local_execution_record_present": True,
        "mock_exchange_record_present": True,
        "real_balance_delta_present": False,
        "real_position_delta_present": False,
        "fee_evidence_present": False,
        "slippage_evidence_present": False,
        "api_latency_evidence_present": False,
        "mismatch_blocks_promotion": True,
        "reconciliation_started": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_4_mock_reconciliation_input_sha256"] = sha256_json(payload)
    return payload


def validate_mock_submit_evidence_flow_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    unsafe = _unsafe_true_fields(data)
    secret_like = _find_secret_like_values(data)
    errors: list[str] = []
    if data.get("review_only") is not True:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REQUIRES_REVIEW_ONLY_TRUE")
    if data.get("mock_evidence_only") is not True:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REQUIRES_MOCK_EVIDENCE_ONLY_TRUE")
    if data.get("actual_order_submission_performed") is not False:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_ACTUAL_SUBMIT_MUST_BE_FALSE")
    if data.get("real_exchange_endpoint_call_performed") is not False:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REAL_ENDPOINT_MUST_BE_FALSE")
    if data.get("phase9_3_status_polling_may_begin") is not False:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REAL_PHASE9_3_MUST_NOT_BEGIN")
    if data.get("phase9_4_testnet_reconciliation_may_begin") is not False:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_REAL_PHASE9_4_MUST_NOT_BEGIN")
    if unsafe:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    if secret_like:
        errors.append("PHASE9_2_MOCK_EVIDENCE_FLOW_SECRET_LIKE_VALUES_PRESENT")
    return {
        "artifact_type": "phase9_2_mock_submit_evidence_flow_validation_report",
        "phase9_2_mock_submit_evidence_flow_version": PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_VERSION,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "review_only": True,
        "mock_evidence_flow_payload_valid": not errors,
        "unsafe_true_fields": unsafe,
        "secret_like_values_detected": bool(secret_like),
        "block_reasons": errors,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "created_at_utc": utc_now_canonical(),
    }


def build_negative_fixture_results() -> dict[str, Any]:
    base = {
        "review_only": True,
        "mock_evidence_only": True,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
    }
    fixtures = {
        "actual_order_submission_true": {**base, "actual_order_submission_performed": True},
        "real_endpoint_call_true": {**base, "real_exchange_endpoint_call_performed": True},
        "phase9_3_may_begin_true": {**base, "phase9_3_status_polling_may_begin": True},
        "order_status_endpoint_called_true": {**base, "order_status_endpoint_called": True},
        "secret_like_value": {**base, "api_secret": "SECRET_VALUE_SHOULD_NOT_APPEAR"},
    }
    results: dict[str, Any] = {}
    for name, payload in fixtures.items():
        validation = validate_mock_submit_evidence_flow_payload(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    output = {
        "artifact_type": "phase9_2_mock_submit_evidence_flow_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_mock_submit_evidence_flow_negative_fixture_results_sha256"] = sha256_json(output)
    return output


def build_phase9_2_mock_submit_evidence_flow_report(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    wrapper = _read_latest_json(cfg, SOURCE_FILE)
    source_ready, source_blockers = _source_ready(wrapper)
    mock_execution = build_phase9_2_mock_execution_evidence(wrapper, created_at_utc=created_at_utc) if source_ready else {}
    mock_status = build_phase9_3_mock_status_input(mock_execution, created_at_utc=created_at_utc) if mock_execution else {}
    mock_reconciliation = build_phase9_4_mock_reconciliation_input(mock_execution, mock_status, created_at_utc=created_at_utc) if mock_status else {}

    validations = [validate_mock_submit_evidence_flow_payload(p) for p in (mock_execution, mock_status, mock_reconciliation) if p]
    validation_blockers = [reason for validation in validations for reason in validation["block_reasons"]]
    blockers = list(source_blockers) + validation_blockers
    handoff_id = stable_id("phase9_2_mock_submit_evidence_flow", {
        "source": _source_summary(wrapper),
        "mock_execution_hash": mock_execution.get("phase9_2_mock_execution_evidence_sha256") if mock_execution else None,
        "mock_status_hash": mock_status.get("phase9_3_mock_status_input_sha256") if mock_status else None,
        "mock_reconciliation_hash": mock_reconciliation.get("phase9_4_mock_reconciliation_input_sha256") if mock_reconciliation else None,
    }, 24)
    report = {
        "artifact_type": "phase9_2_mock_submit_evidence_flow_report",
        "phase9_2_mock_submit_evidence_flow_id": handoff_id,
        "phase9_2_mock_submit_evidence_flow_version": PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_VERSION,
        "status": STATUS_MOCK_SUBMIT_EVIDENCE_FLOW_BLOCKED if blockers else STATUS_MOCK_SUBMIT_EVIDENCE_FLOW_RECORDED,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "mock_evidence_only": True,
        "source_wrapper_summary": _source_summary(wrapper),
        "source_blockers": source_blockers,
        "mock_execution_evidence_created": bool(mock_execution),
        "phase9_3_mock_status_input_created": bool(mock_status),
        "phase9_4_mock_reconciliation_input_created": bool(mock_reconciliation),
        "mock_flow_ready_for_review_only_evidence_intake": bool(mock_execution and mock_status and mock_reconciliation and not blockers),
        "real_phase9_3_status_polling_may_begin": False,
        "real_phase9_4_testnet_reconciliation_may_begin": False,
        "phase10_signed_testnet_session_validation_may_begin": False,
        "block_reasons": blockers,
        "recommended_next_action": "review_mock_flow_outputs_then_keep_real_endpoint_adapter_separate_until_explicit_testnet_submit_approval",
        **_disabled_payload(),
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_mock_submit_evidence_flow_report_sha256"] = sha256_json(report)
    return report, mock_execution, mock_status, mock_reconciliation


def persist_phase9_2_mock_submit_evidence_flow(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, mock_execution, mock_status, mock_reconciliation = build_phase9_2_mock_submit_evidence_flow_report(cfg=cfg)
    validation = validate_mock_submit_evidence_flow_payload(report)
    negative = build_negative_fixture_results()

    files: dict[str, Mapping[str, Any]] = {
        "phase9_2_mock_submit_evidence_flow_report.json": report,
        "phase9_2_mock_submit_evidence_flow_validation_report.json": validation,
        "phase9_2_mock_submit_evidence_flow_negative_fixture_results.json": negative,
    }
    if mock_execution:
        files["phase9_2_mock_execution_EVIDENCE_REVIEW_ONLY.json"] = mock_execution
    if mock_status:
        files["phase9_3_mock_status_input_FROM_PHASE9_2_REVIEW_ONLY.json"] = mock_status
    if mock_reconciliation:
        files["phase9_4_mock_reconciliation_input_FROM_PHASE9_2_REVIEW_ONLY.json"] = mock_reconciliation

    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)

    handoff = "\n".join([
        "# Phase 9.2 Mock Submit Result to Phase 9.3/9.4 Evidence Flow",
        "",
        "This handoff converts the mocked Phase 9.2 runtime submit wrapper result into review-only evidence inputs for Phase 9.3 and Phase 9.4.",
        "It does not authorize real status polling, cancel requests, reconciliation, or exchange endpoint calls.",
        "Mock order IDs are explicitly marked mock-only and must not be used as real exchange order IDs.",
        "Real Phase 9.3/9.4 remains blocked until a separately approved real signed testnet order exists.",
    ])
    (latest / "PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    record = append_registry_record(
        registry_path(cfg, PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_REGISTRY_NAME),
        {
            "artifact_type": "phase9_2_mock_submit_evidence_flow_registry_record",
            "status": report["status"],
            "review_only": True,
            "mock_evidence_only": True,
            "report_sha256": report["phase9_2_mock_submit_evidence_flow_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_REGISTRY_NAME,
        id_field="phase9_2_mock_submit_evidence_flow_registry_id",
        hash_field="phase9_2_mock_submit_evidence_flow_registry_record_sha256",
        id_prefix="phase9_2_mock_submit_evidence_flow_registry",
    )
    atomic_write_json(latest / "phase9_2_mock_submit_evidence_flow_registry_record.json", record)
    return report
