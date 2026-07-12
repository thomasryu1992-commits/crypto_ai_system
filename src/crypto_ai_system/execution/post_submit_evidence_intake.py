from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.execution.single_signed_testnet_submit_runtime_action import (
    STATUS_SUBMITTED_BY_EXTERNAL_RUNTIME as P6_STATUS_SUBMITTED_BY_EXTERNAL_RUNTIME,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P7_POST_SUBMIT_EVIDENCE_INTAKE_VERSION = "p7_post_submit_evidence_intake_v1"
P7_POST_SUBMIT_EVIDENCE_INTAKE_REGISTRY_NAME = "p7_post_submit_evidence_intake_registry"

STATUS_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY = "P7_POST_SUBMIT_EVIDENCE_INTAKE_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY"
STATUS_RECONCILED_SESSION_CLOSED_REVIEW_ONLY = "P7_POST_SUBMIT_EVIDENCE_INTAKE_RECONCILED_SESSION_CLOSED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P7_POST_SUBMIT_EVIDENCE_INTAKE_BLOCKED_FAIL_CLOSED"

_ALLOWED_FINAL_STATUSES = {"NEW", "PARTIALLY_FILLED", "FILLED", "REJECTED", "CANCELED", "EXPIRED"}
_TERMINAL_STATUSES = {"FILLED", "REJECTED", "CANCELED", "EXPIRED"}
_OPEN_STATUSES = {"NEW", "PARTIALLY_FILLED"}

_ALWAYS_DISABLED_FLAGS = {
    "ready_for_signed_testnet_execution": False,
    "testnet_order_submission_allowed": False,
    "signed_testnet_promotion_allowed": False,
    "external_order_submission_allowed": False,
    "place_order_enabled": False,
    "cancel_order_enabled": False,
    "signed_order_executor_enabled": False,
    "runtime_settings_mutated": False,
    "score_weights_mutated": False,
    "candidate_profile_applied": False,
    "auto_promotion_allowed": False,
    "secret_value_accessed": False,
    "secret_value_logged": False,
    "api_key_value_logged": False,
    "api_secret_value_logged": False,
    "private_key_logged": False,
    "passphrase_logged": False,
    "secret_file_accessed": False,
    "secret_file_created": False,
    "live_canary_execution_enabled": False,
    "live_scaled_execution_enabled": False,
    "live_execution_unlock_authority": False,
    "signed_testnet_unlock_authority": False,
    "live_trading_allowed_by_this_module": False,
    "live_order_executed": False,
    "mainnet_key_scope_allowed": False,
    "withdrawal_permission_allowed": False,
    "transfer_permission_allowed": False,
    "admin_permission_allowed": False,
}


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


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _is_nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _looks_mock_or_fixture_identifier(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    blocked_terms = ("mock", "fixture", "sample", "synthetic", "simulated", "dummy", "fake")
    return any(term in text for term in blocked_terms)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _sha_from(payload: Mapping[str, Any], *keys: str) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in keys:
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _disabled_payload(*, external_submit_performed: bool = False, status_endpoint_called: bool = False, cancel_endpoint_called: bool = False) -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED_FLAGS)
    payload.update(
        {
            "external_order_submission_performed": bool(external_submit_performed),
            "actual_order_submission_performed": bool(external_submit_performed),
            "actual_testnet_order_submitted": bool(external_submit_performed),
            "runtime_submit_action_executed": bool(external_submit_performed),
            "runtime_submit_action_performed": bool(external_submit_performed),
            "real_exchange_order_id_present": bool(external_submit_performed),
            "order_endpoint_called": bool(external_submit_performed),
            "order_status_endpoint_called": bool(status_endpoint_called),
            "cancel_endpoint_called": bool(cancel_endpoint_called),
            "http_request_sent": bool(external_submit_performed or status_endpoint_called or cancel_endpoint_called),
            "signature_created": bool(external_submit_performed or status_endpoint_called or cancel_endpoint_called),
            "signed_request_created": bool(external_submit_performed or status_endpoint_called or cancel_endpoint_called),
            "cancel_request_sent": bool(cancel_endpoint_called),
            "reconciliation_started": bool(external_submit_performed),
            "phase10_session_validation_started": False,
            "live_canary_preparation_may_begin": False,
        }
    )
    if not external_submit_performed:
        for key in (
            "external_order_submission_performed",
            "actual_order_submission_performed",
            "actual_testnet_order_submitted",
            "runtime_submit_action_executed",
            "runtime_submit_action_performed",
            "real_exchange_order_id_present",
            "order_endpoint_called",
            "order_status_endpoint_called",
            "cancel_endpoint_called",
            "http_request_sent",
            "signature_created",
            "signed_request_created",
            "cancel_request_sent",
            "reconciliation_started",
        ):
            payload[key] = False
    return payload


@dataclass(frozen=True)
class PostSubmitOrderIdIntakeEvidence:
    source_p6_submit_runtime_action_sha256: str | None = None
    exchange: str = "binance_futures_testnet"
    environment: str = "testnet"
    symbol: str = "BTCUSDT"
    order_count: int = 1
    exchange_order_id: str = "testnet_order_12345"
    client_order_id: str = "p6_single_signed_testnet_submit_idempotency_key"
    idempotency_key: str = "p6_single_signed_testnet_submit_idempotency_key"
    execution_id: str = "execution_signed_testnet_1"
    order_intent_id: str = "order_intent_1"
    risk_gate_id: str = "risk_gate_1"
    request_hash: str = field(default_factory=lambda: "9" * 64)
    exchange_response_hash: str = field(default_factory=lambda: "a" * 64)
    raw_exchange_response_redacted_path: str = "storage/redacted_exchange_responses/testnet_order_12345.json"
    hot_path_preorder_risk_gate_id: str = "risk_gate_1"
    hot_path_preorder_risk_gate_hash: str = field(default_factory=lambda: "d" * 64)
    secret_reference_id: str = "metadata_only_testnet_key_ref_runtime_submit"
    key_fingerprint_sha256: str = field(default_factory=lambda: "e" * 64)
    no_secret_logged_evidence_hash: str = field(default_factory=lambda: "f" * 64)
    evidence_origin: str = "real_signed_testnet_external_runtime"
    mock_or_fixture_evidence: bool = False
    synthetic_or_sample_evidence: bool = False
    order_endpoint_called: bool = True
    http_request_sent: bool = True
    signature_created: bool = True
    signed_request_created: bool = True
    real_exchange_response: bool = True
    secret_value_included: bool = False
    api_key_value_included: bool = False
    api_secret_value_included: bool = False
    private_key_included: bool = False
    passphrase_included: bool = False
    mainnet_key_scope_allowed: bool = False
    withdrawal_permission_allowed: bool = False
    transfer_permission_allowed: bool = False
    admin_permission_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["post_submit_order_id_intake_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class StatusPollingEventEvidence:
    event_id: str = "status_poll_event_1"
    endpoint_type: str = "signed_testnet_private_order_status"
    method: str = "GET"
    exchange_order_id: str = "testnet_order_12345"
    client_order_id: str = "p6_single_signed_testnet_submit_idempotency_key"
    exchange_order_status: str = "FILLED"
    request_hash: str = field(default_factory=lambda: "b" * 64)
    response_hash: str = field(default_factory=lambda: "c" * 64)
    timestamp_utc: str = field(default_factory=utc_now_canonical)
    retry_count: int = 0
    api_latency_ms: int = 120
    rate_limit_status: str = "ok"
    order_status_endpoint_called: bool = True
    http_request_sent: bool = True
    signature_created: bool = True
    signed_request_created: bool = True
    real_exchange_response: bool = True
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status_polling_event_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class CancelBoundaryEvidence:
    cancel_boundary_decision_recorded: bool = True
    exchange_order_id: str = "testnet_order_12345"
    final_status_before_cancel_decision: str = "FILLED"
    cancel_required: bool = False
    cancel_requested: bool = False
    cancel_endpoint_called: bool = False
    cancel_request_sent: bool = False
    cancel_response_hash: str | None = None
    duplicate_cancel_prevented: bool = True
    cancel_final_status: str | None = None
    cancel_block_reason: str | None = "not_required_terminal_status"
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cancel_boundary_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class SignedTestnetReconciliationEvidence:
    reconciliation_id: str = "reconciliation_signed_testnet_1"
    exchange_order_id: str = "testnet_order_12345"
    client_order_id: str = "p6_single_signed_testnet_submit_idempotency_key"
    idempotency_key: str = "p6_single_signed_testnet_submit_idempotency_key"
    execution_id: str = "execution_signed_testnet_1"
    order_intent_id: str = "order_intent_1"
    risk_gate_id: str = "risk_gate_1"
    final_exchange_order_status: str = "FILLED"
    exchange_response_hash_match: bool = True
    status_polling_hash_chain_match: bool = True
    order_intent_match: bool = True
    idempotency_key_match: bool = True
    fee_reconciled: bool = True
    fill_quantity_reconciled: bool = True
    position_delta_reconciled: bool = True
    slippage_recorded: bool = True
    reconciliation_mismatch_count: int = 0
    api_error_count: int = 0
    secret_value_logged: bool = False
    live_position_sync_enabled_by_this_module: bool = False
    live_trading_allowed_by_this_module: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signed_testnet_reconciliation_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class SignedTestnetSessionCloseEvidence:
    session_close_id: str = "signed_testnet_session_close_1"
    exchange_order_id: str = "testnet_order_12345"
    reconciliation_id: str = "reconciliation_signed_testnet_1"
    session_closed: bool = True
    session_close_status: str = "SIGNED_TESTNET_SESSION_CLOSED_CLEAN_REVIEW_ONLY"
    final_exchange_order_status: str = "FILLED"
    reconciliation_clean: bool = True
    no_open_testnet_order_remaining: bool = True
    no_duplicate_submit_detected: bool = True
    post_submit_relock_confirmed: bool = True
    place_order_enabled_after_close: bool = False
    cancel_order_enabled_after_close: bool = False
    signed_order_executor_enabled_after_close: bool = False
    testnet_order_submission_allowed_after_close: bool = False
    signed_testnet_promotion_allowed: bool = False
    live_canary_preparation_allowed: bool = False
    live_canary_execution_enabled: bool = False
    live_scaled_execution_enabled: bool = False
    incident_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signed_testnet_session_close_evidence_sha256"] = sha256_json(payload)
        return payload


def validate_post_submit_order_id_intake(evidence: Mapping[str, Any] | PostSubmitOrderIdIntakeEvidence | None, *, expected_p6_sha256: str | None = None) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, PostSubmitOrderIdIntakeEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if expected_p6_sha256 and payload.get("source_p6_submit_runtime_action_sha256") != expected_p6_sha256:
        blockers.append("P7_SOURCE_P6_SUBMIT_RUNTIME_ACTION_HASH_MISMATCH")
    if payload.get("environment") != "testnet":
        blockers.append("P7_ORDER_ID_INTAKE_ENVIRONMENT_NOT_TESTNET")
    if payload.get("symbol") != "BTCUSDT":
        blockers.append("P7_ORDER_ID_INTAKE_SYMBOL_NOT_BTCUSDT")
    if payload.get("order_count") != 1:
        blockers.append("P7_ORDER_ID_INTAKE_ORDER_COUNT_NOT_ONE")
    for key, reason in (
        ("exchange_order_id", "P7_EXCHANGE_ORDER_ID_MISSING"),
        ("client_order_id", "P7_CLIENT_ORDER_ID_MISSING"),
        ("idempotency_key", "P7_IDEMPOTENCY_KEY_MISSING"),
        ("execution_id", "P7_EXECUTION_ID_MISSING"),
        ("order_intent_id", "P7_ORDER_INTENT_ID_MISSING"),
        ("risk_gate_id", "P7_RISK_GATE_ID_MISSING"),
        ("request_hash", "P7_REQUEST_HASH_MISSING"),
        ("exchange_response_hash", "P7_EXCHANGE_RESPONSE_HASH_MISSING"),
        ("raw_exchange_response_redacted_path", "P7_REDACTED_RESPONSE_PATH_MISSING"),
        ("hot_path_preorder_risk_gate_id", "P7_HOT_PATH_RISK_GATE_ID_MISSING"),
        ("hot_path_preorder_risk_gate_hash", "P7_HOT_PATH_RISK_GATE_HASH_MISSING"),
        ("secret_reference_id", "P7_SECRET_REFERENCE_ID_MISSING"),
        ("key_fingerprint_sha256", "P7_KEY_FINGERPRINT_SHA256_MISSING"),
        ("no_secret_logged_evidence_hash", "P7_NO_SECRET_LOGGED_EVIDENCE_HASH_MISSING"),
    ):
        if not _is_nonempty(payload.get(key)):
            blockers.append(reason)
    for key, reason in (
        ("request_hash", "P7_REQUEST_HASH_NOT_SHA256_HEX"),
        ("exchange_response_hash", "P7_EXCHANGE_RESPONSE_HASH_NOT_SHA256_HEX"),
        ("hot_path_preorder_risk_gate_hash", "P7_HOT_PATH_RISK_GATE_HASH_NOT_SHA256_HEX"),
        ("key_fingerprint_sha256", "P7_KEY_FINGERPRINT_NOT_SHA256_HEX"),
        ("no_secret_logged_evidence_hash", "P7_NO_SECRET_LOGGED_EVIDENCE_HASH_NOT_SHA256_HEX"),
    ):
        if _is_nonempty(payload.get(key)) and not _is_sha256_hex(payload.get(key)):
            blockers.append(reason)
    if _looks_mock_or_fixture_identifier(payload.get("exchange_order_id")):
        blockers.append("P7_EXCHANGE_ORDER_ID_LOOKS_MOCK_OR_FIXTURE")
    if str(payload.get("evidence_origin") or "") != "real_signed_testnet_external_runtime":
        blockers.append("P7_EVIDENCE_ORIGIN_NOT_REAL_SIGNED_TESTNET_EXTERNAL_RUNTIME")
    if payload.get("mock_or_fixture_evidence") is True:
        blockers.append("P7_MOCK_OR_FIXTURE_EVIDENCE_NOT_ALLOWED_AS_REAL_POST_SUBMIT")
    if payload.get("synthetic_or_sample_evidence") is True:
        blockers.append("P7_SYNTHETIC_OR_SAMPLE_EVIDENCE_NOT_ALLOWED_AS_REAL_POST_SUBMIT")
    if payload.get("order_endpoint_called") is not True:
        blockers.append("P7_ORDER_ENDPOINT_CALL_EVIDENCE_MISSING")
    if payload.get("http_request_sent") is not True:
        blockers.append("P7_HTTP_REQUEST_SENT_EVIDENCE_MISSING")
    if payload.get("signature_created") is not True or payload.get("signed_request_created") is not True:
        blockers.append("P7_SIGNED_REQUEST_EVIDENCE_MISSING")
    if payload.get("real_exchange_response") is not True:
        blockers.append("P7_REAL_EXCHANGE_RESPONSE_NOT_CONFIRMED")
    for key, reason in (
        ("secret_value_included", "P7_SECRET_VALUE_INCLUDED_IN_ORDER_ID_INTAKE"),
        ("api_key_value_included", "P7_API_KEY_VALUE_INCLUDED_IN_ORDER_ID_INTAKE"),
        ("api_secret_value_included", "P7_API_SECRET_VALUE_INCLUDED_IN_ORDER_ID_INTAKE"),
        ("private_key_included", "P7_PRIVATE_KEY_INCLUDED_IN_ORDER_ID_INTAKE"),
        ("passphrase_included", "P7_PASSPHRASE_INCLUDED_IN_ORDER_ID_INTAKE"),
        ("mainnet_key_scope_allowed", "P7_MAINNET_KEY_SCOPE_NOT_ALLOWED"),
        ("withdrawal_permission_allowed", "P7_WITHDRAWAL_PERMISSION_NOT_ALLOWED"),
        ("transfer_permission_allowed", "P7_TRANSFER_PERMISSION_NOT_ALLOWED"),
        ("admin_permission_allowed", "P7_ADMIN_PERMISSION_NOT_ALLOWED"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    validation = {
        "post_submit_order_id_intake_valid": not blockers,
        "post_submit_order_id_intake_block_reasons": sorted(dict.fromkeys(blockers)),
        "exchange_order_id": payload.get("exchange_order_id"),
        "client_order_id": payload.get("client_order_id"),
        "idempotency_key": payload.get("idempotency_key"),
        "request_hash_present": _is_nonempty(payload.get("request_hash")),
        "exchange_response_hash_present": _is_nonempty(payload.get("exchange_response_hash")),
        "hot_path_preorder_risk_gate_id": payload.get("hot_path_preorder_risk_gate_id"),
        "secret_reference_id_present": _is_nonempty(payload.get("secret_reference_id")),
        "key_fingerprint_sha256_present": _is_nonempty(payload.get("key_fingerprint_sha256")),
        "evidence_origin": payload.get("evidence_origin"),
        "source_p6_submit_runtime_action_sha256": payload.get("source_p6_submit_runtime_action_sha256"),
        "expected_p6_submit_runtime_action_sha256": expected_p6_sha256,
    }
    validation["post_submit_order_id_intake_validation_sha256"] = sha256_json(validation)
    return validation


def validate_status_polling_evidence(events: Sequence[Mapping[str, Any] | StatusPollingEventEvidence] | None, *, exchange_order_id: str | None = None) -> dict[str, Any]:
    payloads = [event.to_dict() if isinstance(event, StatusPollingEventEvidence) else dict(event or {}) for event in list(events or [])]
    blockers: list[str] = []
    if not payloads:
        blockers.append("P7_STATUS_POLLING_EVENTS_MISSING")
    statuses: list[str] = []
    for index, event in enumerate(payloads):
        prefix = f"P7_STATUS_EVENT_{index}"
        status = str(event.get("exchange_order_status") or "").upper()
        statuses.append(status)
        if exchange_order_id and event.get("exchange_order_id") != exchange_order_id:
            blockers.append(f"{prefix}_EXCHANGE_ORDER_ID_MISMATCH")
        if status not in _ALLOWED_FINAL_STATUSES:
            blockers.append(f"{prefix}_INVALID_ORDER_STATUS")
        for key, reason in (
            ("request_hash", f"{prefix}_REQUEST_HASH_MISSING"),
            ("response_hash", f"{prefix}_RESPONSE_HASH_MISSING"),
            ("timestamp_utc", f"{prefix}_TIMESTAMP_MISSING"),
        ):
            if not _is_nonempty(event.get(key)):
                blockers.append(reason)
        if event.get("order_status_endpoint_called") is not True:
            blockers.append(f"{prefix}_ORDER_STATUS_ENDPOINT_CALL_MISSING")
        if event.get("http_request_sent") is not True:
            blockers.append(f"{prefix}_HTTP_REQUEST_SENT_MISSING")
        if event.get("signature_created") is not True or event.get("signed_request_created") is not True:
            blockers.append(f"{prefix}_SIGNED_REQUEST_EVIDENCE_MISSING")
        if event.get("real_exchange_response") is not True:
            blockers.append(f"{prefix}_REAL_EXCHANGE_RESPONSE_NOT_CONFIRMED")
        if event.get("secret_value_logged") is True:
            blockers.append(f"{prefix}_SECRET_VALUE_LOGGED")
        if event.get("api_key_value_logged") is True:
            blockers.append(f"{prefix}_API_KEY_VALUE_LOGGED")
        if event.get("api_secret_value_logged") is True:
            blockers.append(f"{prefix}_API_SECRET_VALUE_LOGGED")
        retry_count = int(event.get("retry_count", 0) or 0)
        if retry_count < 0 or retry_count > 3:
            blockers.append(f"{prefix}_RETRY_COUNT_OUT_OF_POLICY")
    final_status = statuses[-1] if statuses else None
    if final_status and final_status not in _ALLOWED_FINAL_STATUSES:
        blockers.append("P7_FINAL_STATUS_INVALID")
    validation = {
        "status_polling_evidence_valid": not blockers,
        "status_polling_block_reasons": sorted(dict.fromkeys(blockers)),
        "status_polling_event_count": len(payloads),
        "status_sequence": statuses,
        "final_exchange_order_status": final_status,
        "terminal_status_observed": final_status in _TERMINAL_STATUSES,
        "status_endpoint_called": any(event.get("order_status_endpoint_called") is True for event in payloads),
    }
    validation["status_polling_validation_sha256"] = sha256_json(validation)
    return validation


def validate_cancel_boundary_evidence(evidence: Mapping[str, Any] | CancelBoundaryEvidence | None, *, exchange_order_id: str | None = None, final_status: str | None = None) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, CancelBoundaryEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P7_CANCEL_BOUNDARY_EVIDENCE_MISSING")
    if payload.get("cancel_boundary_decision_recorded") is not True:
        blockers.append("P7_CANCEL_BOUNDARY_DECISION_NOT_RECORDED")
    if exchange_order_id and payload.get("exchange_order_id") != exchange_order_id:
        blockers.append("P7_CANCEL_BOUNDARY_EXCHANGE_ORDER_ID_MISMATCH")
    observed = str(final_status or payload.get("final_status_before_cancel_decision") or "").upper()
    cancel_required = observed in _OPEN_STATUSES
    if cancel_required and payload.get("cancel_required") is not True:
        blockers.append("P7_CANCEL_REQUIRED_FOR_OPEN_STATUS_NOT_MARKED")
    if cancel_required and payload.get("cancel_requested") is True:
        if payload.get("cancel_endpoint_called") is not True or payload.get("cancel_request_sent") is not True:
            blockers.append("P7_CANCEL_REQUESTED_WITHOUT_ENDPOINT_EVIDENCE")
        if not _is_nonempty(payload.get("cancel_response_hash")):
            blockers.append("P7_CANCEL_RESPONSE_HASH_MISSING")
    if cancel_required and payload.get("cancel_requested") is not True and not _is_nonempty(payload.get("cancel_block_reason")):
        blockers.append("P7_CANCEL_REQUIRED_WITHOUT_REQUEST_OR_BLOCK_REASON")
    if not cancel_required and payload.get("cancel_endpoint_called") is True:
        blockers.append("P7_CANCEL_ENDPOINT_CALLED_WHEN_NOT_REQUIRED")
    if payload.get("duplicate_cancel_prevented") is not True:
        blockers.append("P7_DUPLICATE_CANCEL_NOT_PREVENTED")
    if payload.get("secret_value_logged") is True:
        blockers.append("P7_CANCEL_SECRET_VALUE_LOGGED")
    if payload.get("api_key_value_logged") is True:
        blockers.append("P7_CANCEL_API_KEY_VALUE_LOGGED")
    if payload.get("api_secret_value_logged") is True:
        blockers.append("P7_CANCEL_API_SECRET_VALUE_LOGGED")
    validation = {
        "cancel_boundary_evidence_valid": not blockers,
        "cancel_boundary_block_reasons": sorted(dict.fromkeys(blockers)),
        "cancel_required": cancel_required,
        "cancel_requested": payload.get("cancel_requested") is True,
        "cancel_endpoint_called": payload.get("cancel_endpoint_called") is True,
        "duplicate_cancel_prevented": payload.get("duplicate_cancel_prevented") is True,
    }
    validation["cancel_boundary_validation_sha256"] = sha256_json(validation)
    return validation


def validate_signed_testnet_reconciliation_evidence(evidence: Mapping[str, Any] | SignedTestnetReconciliationEvidence | None, *, exchange_order_id: str | None = None, final_status: str | None = None) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, SignedTestnetReconciliationEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P7_RECONCILIATION_EVIDENCE_MISSING")
    if exchange_order_id and payload.get("exchange_order_id") != exchange_order_id:
        blockers.append("P7_RECONCILIATION_EXCHANGE_ORDER_ID_MISMATCH")
    if final_status and str(payload.get("final_exchange_order_status") or "").upper() != str(final_status).upper():
        blockers.append("P7_RECONCILIATION_FINAL_STATUS_MISMATCH")
    for key, reason in (
        ("reconciliation_id", "P7_RECONCILIATION_ID_MISSING"),
        ("execution_id", "P7_RECONCILIATION_EXECUTION_ID_MISSING"),
        ("order_intent_id", "P7_RECONCILIATION_ORDER_INTENT_ID_MISSING"),
        ("risk_gate_id", "P7_RECONCILIATION_RISK_GATE_ID_MISSING"),
        ("idempotency_key", "P7_RECONCILIATION_IDEMPOTENCY_KEY_MISSING"),
    ):
        if not _is_nonempty(payload.get(key)):
            blockers.append(reason)
    for key, reason in (
        ("exchange_response_hash_match", "P7_RECONCILIATION_EXCHANGE_RESPONSE_HASH_MISMATCH"),
        ("status_polling_hash_chain_match", "P7_RECONCILIATION_STATUS_HASH_CHAIN_MISMATCH"),
        ("order_intent_match", "P7_RECONCILIATION_ORDER_INTENT_MISMATCH"),
        ("idempotency_key_match", "P7_RECONCILIATION_IDEMPOTENCY_KEY_MISMATCH"),
        ("fee_reconciled", "P7_RECONCILIATION_FEE_NOT_RECONCILED"),
        ("fill_quantity_reconciled", "P7_RECONCILIATION_FILL_QUANTITY_NOT_RECONCILED"),
        ("position_delta_reconciled", "P7_RECONCILIATION_POSITION_DELTA_NOT_RECONCILED"),
        ("slippage_recorded", "P7_RECONCILIATION_SLIPPAGE_NOT_RECORDED"),
    ):
        if payload.get(key) is not True:
            blockers.append(reason)
    mismatch_count = int(payload.get("reconciliation_mismatch_count", 999)) if payload.get("reconciliation_mismatch_count") is not None else 999
    api_error_count = int(payload.get("api_error_count", 999)) if payload.get("api_error_count") is not None else 999
    if mismatch_count != 0:
        blockers.append("P7_RECONCILIATION_MISMATCH_COUNT_NONZERO")
    if api_error_count > 0:
        blockers.append("P7_RECONCILIATION_API_ERROR_COUNT_NONZERO")
    if payload.get("secret_value_logged") is True:
        blockers.append("P7_RECONCILIATION_SECRET_VALUE_LOGGED")
    if payload.get("live_position_sync_enabled_by_this_module") is True:
        blockers.append("P7_RECONCILIATION_LIVE_POSITION_SYNC_NOT_ALLOWED")
    if payload.get("live_trading_allowed_by_this_module") is True:
        blockers.append("P7_RECONCILIATION_LIVE_TRADING_NOT_ALLOWED")
    validation = {
        "signed_testnet_reconciliation_evidence_valid": not blockers,
        "signed_testnet_reconciliation_block_reasons": sorted(dict.fromkeys(blockers)),
        "reconciliation_id": payload.get("reconciliation_id"),
        "reconciliation_mismatch_count": payload.get("reconciliation_mismatch_count"),
        "api_error_count": payload.get("api_error_count"),
    }
    validation["signed_testnet_reconciliation_validation_sha256"] = sha256_json(validation)
    return validation


def validate_signed_testnet_session_close_evidence(evidence: Mapping[str, Any] | SignedTestnetSessionCloseEvidence | None, *, exchange_order_id: str | None = None, reconciliation_id: str | None = None, final_status: str | None = None) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, SignedTestnetSessionCloseEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P7_SESSION_CLOSE_EVIDENCE_MISSING")
    if exchange_order_id and payload.get("exchange_order_id") != exchange_order_id:
        blockers.append("P7_SESSION_CLOSE_EXCHANGE_ORDER_ID_MISMATCH")
    if reconciliation_id and payload.get("reconciliation_id") != reconciliation_id:
        blockers.append("P7_SESSION_CLOSE_RECONCILIATION_ID_MISMATCH")
    if final_status and str(payload.get("final_exchange_order_status") or "").upper() != str(final_status).upper():
        blockers.append("P7_SESSION_CLOSE_FINAL_STATUS_MISMATCH")
    required_true = {
        "session_closed": "P7_SESSION_NOT_CLOSED",
        "reconciliation_clean": "P7_SESSION_RECONCILIATION_NOT_CLEAN",
        "no_open_testnet_order_remaining": "P7_OPEN_TESTNET_ORDER_REMAINING",
        "no_duplicate_submit_detected": "P7_DUPLICATE_SUBMIT_DETECTED",
        "post_submit_relock_confirmed": "P7_POST_SUBMIT_RELOCK_NOT_CONFIRMED",
    }
    for key, reason in required_true.items():
        if payload.get(key) is not True:
            blockers.append(reason)
    required_false = {
        "place_order_enabled_after_close": "P7_PLACE_ORDER_ENABLED_AFTER_CLOSE",
        "cancel_order_enabled_after_close": "P7_CANCEL_ORDER_ENABLED_AFTER_CLOSE",
        "signed_order_executor_enabled_after_close": "P7_SIGNED_EXECUTOR_ENABLED_AFTER_CLOSE",
        "testnet_order_submission_allowed_after_close": "P7_TESTNET_SUBMISSION_ALLOWED_AFTER_CLOSE",
        "signed_testnet_promotion_allowed": "P7_SIGNED_TESTNET_PROMOTION_NOT_ALLOWED",
        "live_canary_preparation_allowed": "P7_LIVE_CANARY_PREPARATION_NOT_ALLOWED",
        "live_canary_execution_enabled": "P7_LIVE_CANARY_EXECUTION_ENABLED",
        "live_scaled_execution_enabled": "P7_LIVE_SCALED_EXECUTION_ENABLED",
    }
    for key, reason in required_false.items():
        if payload.get(key) is not False:
            blockers.append(reason)
    validation = {
        "signed_testnet_session_close_evidence_valid": not blockers,
        "signed_testnet_session_close_block_reasons": sorted(dict.fromkeys(blockers)),
        "session_close_id": payload.get("session_close_id"),
        "session_closed": payload.get("session_closed") is True,
        "session_close_status": payload.get("session_close_status"),
        "signed_testnet_promotion_allowed": payload.get("signed_testnet_promotion_allowed") is True,
        "live_canary_preparation_allowed": payload.get("live_canary_preparation_allowed") is True,
    }
    validation["signed_testnet_session_close_validation_sha256"] = sha256_json(validation)
    return validation


def _p6_submission_state(p6_report: Mapping[str, Any]) -> tuple[bool, bool, list[str]]:
    data = dict(p6_report or {})
    blockers: list[str] = []
    if not data:
        return False, False, ["P7_SOURCE_P6_REPORT_MISSING"]
    p6_submitted = data.get("status") == P6_STATUS_SUBMITTED_BY_EXTERNAL_RUNTIME or data.get("actual_testnet_order_submitted") is True
    p6_ready_waiting = data.get("status") == "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_READY_DISABLED_NO_SUBMIT"
    if not p6_submitted and not p6_ready_waiting:
        blockers.append("P7_SOURCE_P6_STATUS_NOT_SUBMITTED_OR_READY_WAITING")
    if p6_submitted:
        for key, reason in (
            ("actual_order_submission_performed", "P7_P6_ACTUAL_SUBMISSION_NOT_TRUE"),
            ("order_endpoint_called", "P7_P6_ORDER_ENDPOINT_CALLED_NOT_TRUE"),
            ("http_request_sent", "P7_P6_HTTP_REQUEST_SENT_NOT_TRUE"),
            ("signature_created", "P7_P6_SIGNATURE_CREATED_NOT_TRUE"),
            ("signed_request_created", "P7_P6_SIGNED_REQUEST_CREATED_NOT_TRUE"),
            ("real_exchange_order_id_present", "P7_P6_REAL_EXCHANGE_ORDER_ID_NOT_TRUE"),
        ):
            if data.get(key) is not True:
                blockers.append(reason)
        for key, reason in (
            ("secret_value_accessed", "P7_P6_SECRET_VALUE_ACCESSED"),
            ("secret_value_logged", "P7_P6_SECRET_VALUE_LOGGED"),
            ("testnet_order_submission_allowed", "P7_P6_TESTNET_SUBMISSION_ALLOWED_REMAINED_TRUE"),
            ("live_canary_execution_enabled", "P7_P6_LIVE_CANARY_ENABLED"),
            ("live_scaled_execution_enabled", "P7_P6_LIVE_SCALED_ENABLED"),
        ):
            if data.get(key) is True:
                blockers.append(reason)
    return p6_submitted, p6_ready_waiting, blockers


def build_post_submit_evidence_intake_report(
    *,
    cfg: AppConfig | None = None,
    p6_report: Mapping[str, Any] | None = None,
    order_id_intake: Mapping[str, Any] | PostSubmitOrderIdIntakeEvidence | None = None,
    status_polling_events: Sequence[Mapping[str, Any] | StatusPollingEventEvidence] | None = None,
    cancel_boundary: Mapping[str, Any] | CancelBoundaryEvidence | None = None,
    reconciliation_evidence: Mapping[str, Any] | SignedTestnetReconciliationEvidence | None = None,
    session_close_evidence: Mapping[str, Any] | SignedTestnetSessionCloseEvidence | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    source_p6 = dict(p6_report or _read_latest_json(cfg, "p6_single_signed_testnet_submit_runtime_action_report.json"))
    source_p6_sha256 = _sha_from(source_p6, "p6_single_signed_testnet_submit_runtime_action_sha256", "p6_summary_sha256", "report_sha256")
    p6_submitted, p6_ready_waiting, p6_blockers = _p6_submission_state(source_p6)

    if not p6_submitted:
        report = {
            "artifact_type": "p7_post_submit_evidence_intake",
            "p7_post_submit_evidence_intake_version": P7_POST_SUBMIT_EVIDENCE_INTAKE_VERSION,
            "status": STATUS_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY if p6_ready_waiting and not p6_blockers else STATUS_BLOCKED_FAIL_CLOSED,
            "blocked": bool(p6_blockers),
            "fail_closed": bool(p6_blockers),
            "review_only": True,
            "source_p6_submit_runtime_action_present": bool(source_p6),
            "source_p6_submit_runtime_action_status": source_p6.get("status"),
            "source_p6_submit_runtime_action_sha256": source_p6_sha256,
            "external_submit_evidence_present": False,
            "post_submit_chain_complete": False,
            "post_submit_order_id_intake_required": False,
            "status_polling_required": False,
            "cancel_boundary_required": False,
            "signed_testnet_reconciliation_required": False,
            "signed_testnet_session_close_required": False,
            "next_required_action": "WAIT_FOR_SEPARATELY_APPROVED_EXTERNAL_SINGLE_SIGNED_TESTNET_SUBMIT_EVIDENCE",
            "block_reasons": sorted(dict.fromkeys(p6_blockers)),
            "created_at_utc": created_at_utc,
            **_disabled_payload(),
        }
        report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
        if report["unsafe_truthy_execution_flags"]:
            report["status"] = STATUS_BLOCKED_FAIL_CLOSED
            report["blocked"] = True
            report["fail_closed"] = True
            report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P7_UNSAFE_TRUTHY_EXECUTION_FLAGS_IN_WAITING_STATE"]))
        report["p7_post_submit_evidence_intake_id"] = stable_id("p7_post_submit_evidence_intake", report, 24)
        report["p7_post_submit_evidence_intake_sha256"] = sha256_json(report)
        return report

    order_validation = validate_post_submit_order_id_intake(order_id_intake, expected_p6_sha256=source_p6_sha256)
    exchange_order_id = order_validation.get("exchange_order_id")
    status_validation = validate_status_polling_evidence(status_polling_events, exchange_order_id=str(exchange_order_id or ""))
    final_status = status_validation.get("final_exchange_order_status")
    cancel_validation = validate_cancel_boundary_evidence(cancel_boundary, exchange_order_id=str(exchange_order_id or ""), final_status=str(final_status or ""))
    reconciliation_validation = validate_signed_testnet_reconciliation_evidence(
        reconciliation_evidence,
        exchange_order_id=str(exchange_order_id or ""),
        final_status=str(final_status or ""),
    )
    reconciliation_id = reconciliation_validation.get("reconciliation_id")
    session_close_validation = validate_signed_testnet_session_close_evidence(
        session_close_evidence,
        exchange_order_id=str(exchange_order_id or ""),
        reconciliation_id=str(reconciliation_id or ""),
        final_status=str(final_status or ""),
    )

    blockers = sorted(
        dict.fromkeys(
            p6_blockers
            + list(order_validation["post_submit_order_id_intake_block_reasons"])
            + list(status_validation["status_polling_block_reasons"])
            + list(cancel_validation["cancel_boundary_block_reasons"])
            + list(reconciliation_validation["signed_testnet_reconciliation_block_reasons"])
            + list(session_close_validation["signed_testnet_session_close_block_reasons"])
        )
    )
    chain_complete = bool(
        p6_submitted
        and order_validation["post_submit_order_id_intake_valid"]
        and status_validation["status_polling_evidence_valid"]
        and cancel_validation["cancel_boundary_evidence_valid"]
        and reconciliation_validation["signed_testnet_reconciliation_evidence_valid"]
        and session_close_validation["signed_testnet_session_close_evidence_valid"]
        and not blockers
    )
    status = STATUS_RECONCILED_SESSION_CLOSED_REVIEW_ONLY if chain_complete else STATUS_BLOCKED_FAIL_CLOSED
    report = {
        "artifact_type": "p7_post_submit_evidence_intake",
        "p7_post_submit_evidence_intake_version": P7_POST_SUBMIT_EVIDENCE_INTAKE_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "source_p6_submit_runtime_action_present": bool(source_p6),
        "source_p6_submit_runtime_action_status": source_p6.get("status"),
        "source_p6_submit_runtime_action_sha256": source_p6_sha256,
        "external_submit_evidence_present": p6_submitted,
        "post_submit_chain_complete": chain_complete,
        "post_submit_order_id_intake_validation": order_validation,
        "status_polling_validation": status_validation,
        "cancel_boundary_validation": cancel_validation,
        "signed_testnet_reconciliation_validation": reconciliation_validation,
        "signed_testnet_session_close_validation": session_close_validation,
        "final_exchange_order_status": final_status,
        "terminal_status_observed": status_validation["terminal_status_observed"],
        "post_submit_order_id_intake_required": True,
        "status_polling_required": True,
        "cancel_boundary_required": True,
        "signed_testnet_reconciliation_required": True,
        "signed_testnet_session_close_required": True,
        "signed_testnet_session_closed_clean_review_only": chain_complete,
        "signed_testnet_promotion_allowed": False,
        "live_canary_preparation_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "block_reasons": blockers,
        "created_at_utc": created_at_utc,
        **_disabled_payload(
            external_submit_performed=True,
            status_endpoint_called=status_validation["status_endpoint_called"],
            cancel_endpoint_called=cancel_validation["cancel_endpoint_called"],
        ),
    }
    report["unsafe_truthy_execution_flags"] = [] if chain_complete else truthy_execution_flags(report)
    if not chain_complete and report["unsafe_truthy_execution_flags"]:
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P7_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p7_post_submit_evidence_intake_id"] = stable_id("p7_post_submit_evidence_intake", report, 24)
    report["p7_post_submit_evidence_intake_sha256"] = sha256_json(report)
    return report


def _submitted_p6_fixture(*, p6_hash: str = "7" * 64) -> dict[str, Any]:
    payload = {
        "status": P6_STATUS_SUBMITTED_BY_EXTERNAL_RUNTIME,
        "p6_single_signed_testnet_submit_runtime_action_id": "p6_external_submit_fixture",
        "p6_single_signed_testnet_submit_runtime_action_sha256": p6_hash,
        "actual_order_submission_performed": True,
        "actual_testnet_order_submitted": True,
        "external_order_submission_performed": True,
        "order_endpoint_called": True,
        "http_request_sent": True,
        "signature_created": True,
        "signed_request_created": True,
        "real_exchange_order_id_present": True,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "testnet_order_submission_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }
    return payload


def build_p7_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p6 = _submitted_p6_fixture()
    p6_hash = p6["p6_single_signed_testnet_submit_runtime_action_sha256"]
    valid_order = PostSubmitOrderIdIntakeEvidence(source_p6_submit_runtime_action_sha256=p6_hash)
    valid_status = [StatusPollingEventEvidence()]
    valid_cancel = CancelBoundaryEvidence()
    valid_recon = SignedTestnetReconciliationEvidence()
    valid_close = SignedTestnetSessionCloseEvidence()
    cases: dict[str, dict[str, Any]] = {
        "missing_exchange_order_id": {
            "order": {**valid_order.to_dict(), "exchange_order_id": ""},
            "status": valid_status,
            "cancel": valid_cancel,
            "recon": valid_recon,
            "close": valid_close,
        },
        "p6_hash_mismatch": {
            "order": {**valid_order.to_dict(), "source_p6_submit_runtime_action_sha256": "8" * 64},
            "status": valid_status,
            "cancel": valid_cancel,
            "recon": valid_recon,
            "close": valid_close,
        },
        "status_endpoint_secret_leak": {
            "order": valid_order,
            "status": [{**StatusPollingEventEvidence().to_dict(), "secret_value_logged": True}],
            "cancel": valid_cancel,
            "recon": valid_recon,
            "close": valid_close,
        },
        "cancel_required_without_decision": {
            "order": valid_order,
            "status": [StatusPollingEventEvidence(exchange_order_status="NEW")],
            "cancel": CancelBoundaryEvidence(final_status_before_cancel_decision="NEW", cancel_required=False, cancel_requested=False, cancel_block_reason=None),
            "recon": SignedTestnetReconciliationEvidence(final_exchange_order_status="NEW"),
            "close": SignedTestnetSessionCloseEvidence(final_exchange_order_status="NEW"),
        },
        "reconciliation_mismatch": {
            "order": valid_order,
            "status": valid_status,
            "cancel": valid_cancel,
            "recon": SignedTestnetReconciliationEvidence(reconciliation_mismatch_count=1),
            "close": valid_close,
        },
        "session_close_promotion_enabled": {
            "order": valid_order,
            "status": valid_status,
            "cancel": valid_cancel,
            "recon": valid_recon,
            "close": SignedTestnetSessionCloseEvidence(signed_testnet_promotion_allowed=True),
        },
        "mainnet_scope_in_order_intake": {
            "order": {**valid_order.to_dict(), "environment": "mainnet", "mainnet_key_scope_allowed": True},
            "status": valid_status,
            "cancel": valid_cancel,
            "recon": valid_recon,
            "close": valid_close,
        },
        "fixture_evidence_marked_as_real": {
            "order": {**valid_order.to_dict(), "exchange_order_id": "mock_order_123", "mock_or_fixture_evidence": True},
            "status": valid_status,
            "cancel": valid_cancel,
            "recon": valid_recon,
            "close": valid_close,
        },
        "missing_request_hash_and_secret_reference": {
            "order": {**valid_order.to_dict(), "request_hash": "", "secret_reference_id": ""},
            "status": valid_status,
            "cancel": valid_cancel,
            "recon": valid_recon,
            "close": valid_close,
        },
    }
    results: dict[str, Any] = {}
    for name, fixture in cases.items():
        report = build_post_submit_evidence_intake_report(
            cfg=cfg,
            p6_report=p6,
            order_id_intake=fixture["order"],
            status_polling_events=fixture["status"],
            cancel_boundary=fixture["cancel"],
            reconciliation_evidence=fixture["recon"],
            session_close_evidence=fixture["close"],
        )
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "post_submit_chain_complete": report["post_submit_chain_complete"],
            "signed_testnet_promotion_allowed": report.get("signed_testnet_promotion_allowed", False),
            "live_canary_execution_enabled": report.get("live_canary_execution_enabled", False),
        }
    payload = {
        "artifact_type": "p7_post_submit_evidence_intake_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "default_latest_p7_writes_no_order_endpoint_calls": True,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        **_disabled_payload(),
    }
    payload["p7_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_post_submit_evidence_intake(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_post_submit_evidence_intake_report(cfg=cfg)
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p7_post_submit_evidence_intake")
    negative = build_p7_negative_fixture_results(cfg=cfg)
    registry_record = append_registry_record(
        registry_path(cfg, P7_POST_SUBMIT_EVIDENCE_INTAKE_REGISTRY_NAME),
        {
            "artifact_type": "p7_post_submit_evidence_intake_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p7_post_submit_evidence_intake_id": report["p7_post_submit_evidence_intake_id"],
            "p7_post_submit_evidence_intake_sha256": report["p7_post_submit_evidence_intake_sha256"],
            "source_p6_submit_runtime_action_sha256": report.get("source_p6_submit_runtime_action_sha256"),
            "external_submit_evidence_present": report["external_submit_evidence_present"],
            "post_submit_chain_complete": report["post_submit_chain_complete"],
            "actual_order_submission_performed": report["actual_order_submission_performed"],
            "order_endpoint_called": report["order_endpoint_called"],
            "order_status_endpoint_called": report["order_status_endpoint_called"],
            "cancel_endpoint_called": report["cancel_endpoint_called"],
            "signed_testnet_promotion_allowed": report.get("signed_testnet_promotion_allowed", False),
            "live_canary_execution_enabled": report["live_canary_execution_enabled"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "secret_value_accessed": report["secret_value_accessed"],
        },
        registry_name=P7_POST_SUBMIT_EVIDENCE_INTAKE_REGISTRY_NAME,
        id_field="p7_post_submit_evidence_intake_registry_record_id",
        hash_field="p7_post_submit_evidence_intake_registry_record_sha256",
        id_prefix="p7_post_submit_evidence_intake_registry_record",
    )
    report["p7_post_submit_evidence_intake_registry_record_id"] = registry_record["p7_post_submit_evidence_intake_registry_record_id"]
    report["p7_post_submit_evidence_intake_registry_record_sha256"] = registry_record["p7_post_submit_evidence_intake_registry_record_sha256"]
    report["p7_post_submit_evidence_intake_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p7_post_submit_evidence_intake_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "external_submit_evidence_present": report["external_submit_evidence_present"],
        "post_submit_chain_complete": report["post_submit_chain_complete"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "actual_testnet_order_submitted": report["actual_testnet_order_submitted"],
        "order_endpoint_called": report["order_endpoint_called"],
        "order_status_endpoint_called": report["order_status_endpoint_called"],
        "cancel_endpoint_called": report["cancel_endpoint_called"],
        "secret_value_accessed": report["secret_value_accessed"],
        "signed_testnet_promotion_allowed": report.get("signed_testnet_promotion_allowed", False),
        "live_canary_preparation_allowed": report.get("live_canary_preparation_allowed", False),
        "live_canary_execution_enabled": report["live_canary_execution_enabled"],
        "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p7_post_submit_evidence_intake_id": report["p7_post_submit_evidence_intake_id"],
        "p7_post_submit_evidence_intake_sha256": report["p7_post_submit_evidence_intake_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p7_summary_sha256"] = sha256_json(summary)
    for path in [
        latest / "p7_post_submit_evidence_intake_report.json",
        storage / "p7_post_submit_evidence_intake_report.json",
    ]:
        atomic_write_json(path, report)
    atomic_write_json(latest / "p7_post_submit_evidence_intake_negative_fixture_results.json", negative)
    atomic_write_json(storage / "p7_post_submit_evidence_intake_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p7_post_submit_evidence_intake_registry_record.json", registry_record)
    atomic_write_json(storage / "p7_post_submit_evidence_intake_registry_record.json", registry_record)
    atomic_write_json(latest / "p7_post_submit_evidence_intake_summary.json", summary)
    atomic_write_json(storage / "p7_post_submit_evidence_intake_summary.json", summary)
    return report


__all__ = [
    "P7_POST_SUBMIT_EVIDENCE_INTAKE_VERSION",
    "STATUS_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY",
    "STATUS_RECONCILED_SESSION_CLOSED_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "PostSubmitOrderIdIntakeEvidence",
    "StatusPollingEventEvidence",
    "CancelBoundaryEvidence",
    "SignedTestnetReconciliationEvidence",
    "SignedTestnetSessionCloseEvidence",
    "validate_post_submit_order_id_intake",
    "validate_status_polling_evidence",
    "validate_cancel_boundary_evidence",
    "validate_signed_testnet_reconciliation_evidence",
    "validate_signed_testnet_session_close_evidence",
    "build_post_submit_evidence_intake_report",
    "build_p7_negative_fixture_results",
    "persist_post_submit_evidence_intake",
]
