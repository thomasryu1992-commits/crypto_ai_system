from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.live_canary_one_order_execution_boundary import (
    STATUS_READY_REVIEW_ONLY_NO_SUBMIT as P10_READY,
    build_valid_p10_fixture_sources,
    build_p10_live_canary_one_order_execution_boundary_report,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_VERSION = "p11_live_canary_post_submit_evidence_review_v1"
P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_REGISTRY_NAME = "p11_live_canary_post_submit_evidence_review_registry"

STATUS_WAITING_REVIEW_ONLY = "P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_WAITING_REVIEW_ONLY"
STATUS_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY = "P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_BLOCKED_FAIL_CLOSED"

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
    "live_trading_allowed_by_this_module": False,
    "live_order_submission_allowed": False,
    "live_scaled_promotion_allowed": False,
    "live_scaled_readiness_allowed": False,
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


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _sha_from(payload: Mapping[str, Any], *keys: str) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in keys:
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _disabled_payload(
    *,
    external_live_submit_performed: bool = False,
    status_endpoint_called: bool = False,
    cancel_endpoint_called: bool = False,
) -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED_FLAGS)
    payload.update(
        {
            "external_order_submission_performed": bool(external_live_submit_performed),
            "actual_order_submission_performed": bool(external_live_submit_performed),
            "actual_live_order_submitted": bool(external_live_submit_performed),
            "live_canary_order_submitted": bool(external_live_submit_performed),
            "live_order_endpoint_called": bool(external_live_submit_performed),
            "order_endpoint_called": bool(external_live_submit_performed),
            "live_order_status_endpoint_called": bool(status_endpoint_called),
            "order_status_endpoint_called": bool(status_endpoint_called),
            "live_cancel_endpoint_called": bool(cancel_endpoint_called),
            "cancel_endpoint_called": bool(cancel_endpoint_called),
            "cancel_request_sent": bool(cancel_endpoint_called),
            "http_request_sent": bool(external_live_submit_performed or status_endpoint_called or cancel_endpoint_called),
            "signature_created": bool(external_live_submit_performed or status_endpoint_called or cancel_endpoint_called),
            "signed_request_created": bool(external_live_submit_performed or status_endpoint_called or cancel_endpoint_called),
            "post_submit_relock_confirmed": bool(external_live_submit_performed),
            "live_canary_post_submit_review_started": bool(external_live_submit_performed),
            "live_scaled_readiness_may_begin": False,
        }
    )
    if not external_live_submit_performed:
        for key in (
            "external_order_submission_performed",
            "actual_order_submission_performed",
            "actual_live_order_submitted",
            "live_canary_order_submitted",
            "live_order_endpoint_called",
            "order_endpoint_called",
            "live_order_status_endpoint_called",
            "order_status_endpoint_called",
            "live_cancel_endpoint_called",
            "cancel_endpoint_called",
            "cancel_request_sent",
            "http_request_sent",
            "signature_created",
            "signed_request_created",
            "post_submit_relock_confirmed",
            "live_canary_post_submit_review_started",
        ):
            payload[key] = False
    return payload


@dataclass(frozen=True)
class LiveCanaryOrderSubmissionEvidence:
    source_p10_live_canary_boundary_sha256: str | None = None
    exchange: str = "binance_futures_live"
    environment: str = "live_canary"
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    order_type: str = "MARKET"
    order_count: int = 1
    exchange_order_id: str = "live_canary_order_12345"
    client_order_id: str = "p10_live_canary_idempotency_key"
    idempotency_key: str = "p10_live_canary_idempotency_key"
    execution_id: str = "execution_live_canary_1"
    order_intent_id: str = "order_intent_live_canary_fixture"
    risk_gate_id: str = "risk_gate_live_canary_fixture"
    notional_usdt: float = 5.0
    max_notional_usdt: float = 5.0
    exchange_response_hash: str = field(default_factory=lambda: "a" * 64)
    request_hash: str = field(default_factory=lambda: "b" * 64)
    response_hash: str = field(default_factory=lambda: "c" * 64)
    raw_exchange_response_redacted_path: str = "storage/redacted_exchange_responses/live_canary_order_12345.json"
    actual_live_order_submitted: bool = True
    live_order_endpoint_called: bool = True
    order_endpoint_called: bool = True
    http_request_sent: bool = True
    signature_created: bool = True
    signed_request_created: bool = True
    real_exchange_response: bool = True
    submitted_by_this_module: bool = False
    secret_value_included: bool = False
    api_key_value_included: bool = False
    api_secret_value_included: bool = False
    private_key_included: bool = False
    passphrase_included: bool = False
    secret_value_logged: bool = False
    mainnet_key_scope_allowed: bool = False
    withdrawal_permission_allowed: bool = False
    transfer_permission_allowed: bool = False
    admin_permission_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["live_canary_order_submission_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LiveCanaryStatusPollingEvidence:
    event_id: str = "live_canary_status_poll_event_1"
    endpoint_type: str = "live_private_order_status"
    method: str = "GET"
    exchange_order_id: str = "live_canary_order_12345"
    client_order_id: str = "p10_live_canary_idempotency_key"
    exchange_order_status: str = "FILLED"
    request_hash: str = field(default_factory=lambda: "d" * 64)
    response_hash: str = field(default_factory=lambda: "e" * 64)
    timestamp_utc: str = field(default_factory=utc_now_canonical)
    retry_count: int = 0
    api_latency_ms: int = 150
    rate_limit_status: str = "ok"
    live_order_status_endpoint_called: bool = True
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
        payload["live_canary_status_polling_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LiveCanaryCancelBoundaryEvidence:
    cancel_boundary_decision_recorded: bool = True
    exchange_order_id: str = "live_canary_order_12345"
    final_status_before_cancel_decision: str = "FILLED"
    cancel_required: bool = False
    cancel_requested: bool = False
    live_cancel_endpoint_called: bool = False
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
        payload["live_canary_cancel_boundary_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LiveCanaryReconciliationEvidence:
    live_canary_reconciliation_id: str = "live_canary_reconciliation_1"
    exchange_order_id: str = "live_canary_order_12345"
    client_order_id: str = "p10_live_canary_idempotency_key"
    idempotency_key: str = "p10_live_canary_idempotency_key"
    execution_id: str = "execution_live_canary_1"
    order_intent_id: str = "order_intent_live_canary_fixture"
    risk_gate_id: str = "risk_gate_live_canary_fixture"
    final_exchange_order_status: str = "FILLED"
    submitted_to_exchange: bool = True
    exchange_response_hash_match: bool = True
    status_polling_hash_chain_match: bool = True
    order_intent_match: bool = True
    idempotency_key_match: bool = True
    fee_reconciled: bool = True
    fill_quantity_reconciled: bool = True
    position_delta_reconciled: bool = True
    slippage_recorded: bool = True
    paper_live_gap: float = 0.0
    slippage_bps: float = 1.0
    latency_ms: int = 150
    reconciliation_mismatch_count: int = 0
    api_error_count: int = 0
    rejection_count: int = 0
    manual_override_count: int = 0
    duplicate_submit_detected: bool = False
    unintended_second_order_detected: bool = False
    secret_value_logged: bool = False
    external_position_sync_performed_by_this_module: bool = False
    live_trading_allowed_by_this_module: bool = False
    live_scaled_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["live_canary_reconciliation_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LiveCanaryOutcomeReviewEvidence:
    canary_outcome_report_id: str = "canary_outcome_report_1"
    live_canary_reconciliation_id: str = "live_canary_reconciliation_1"
    outcome_review_completed: bool = True
    canary_outcome_clean: bool = True
    post_submit_relock_confirmed: bool = True
    monitoring_alerting_ready: bool = True
    monitoring_critical_alert_count: int = 0
    deployment_runbook_ready: bool = True
    rollback_runbook_ready: bool = True
    kill_switch_rechecked_after_submit: bool = True
    manual_kill_switch_active_after_submit: bool = False
    incident_required: bool = False
    slippage_within_threshold: bool = True
    latency_within_threshold: bool = True
    api_error_rate_within_threshold: bool = True
    rejection_rate_within_threshold: bool = True
    live_scaled_readiness_candidate_created: bool = False
    live_scaled_promotion_allowed: bool = False
    live_scaled_execution_enabled: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False
    secret_value_accessed: bool = False
    secret_value_logged: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["live_canary_outcome_review_evidence_sha256"] = sha256_json(payload)
        return payload


def _p10_boundary_state(p10_report: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not p10_report:
        return False, ["P11_BLOCK_P10_LIVE_CANARY_EXECUTION_BOUNDARY_MISSING"]
    if p10_report.get("status") != P10_READY or p10_report.get("p10_live_canary_one_order_execution_boundary_ready") is not True:
        blockers.append("P11_BLOCK_P10_LIVE_CANARY_EXECUTION_BOUNDARY_NOT_READY")
    if p10_report.get("live_canary_execution_enabled") is not False or p10_report.get("live_scaled_execution_enabled") is not False:
        blockers.append("P11_BLOCK_P10_UNSAFE_LIVE_FLAGS")
    if _bool(p10_report.get("actual_live_order_submitted")) or _bool(p10_report.get("live_order_endpoint_called")):
        blockers.append("P11_BLOCK_P10_BOUNDARY_ALREADY_SUBMITTED_ORDER")
    if _bool(p10_report.get("secret_value_accessed")) or _bool(p10_report.get("secret_value_logged")):
        blockers.append("P11_BLOCK_P10_SECRET_LEAK")
    return not blockers, sorted(dict.fromkeys(blockers))


def validate_live_canary_order_submission_evidence(
    evidence: Mapping[str, Any] | LiveCanaryOrderSubmissionEvidence | None,
    *,
    expected_p10_sha256: str | None = None,
) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, LiveCanaryOrderSubmissionEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P11_LIVE_CANARY_ORDER_SUBMISSION_EVIDENCE_MISSING")
    if expected_p10_sha256 and payload.get("source_p10_live_canary_boundary_sha256") != expected_p10_sha256:
        blockers.append("P11_SOURCE_P10_BOUNDARY_HASH_MISMATCH")
    if payload.get("environment") != "live_canary":
        blockers.append("P11_ORDER_SUBMISSION_ENVIRONMENT_NOT_LIVE_CANARY")
    if payload.get("exchange") != "binance_futures_live":
        blockers.append("P11_ORDER_SUBMISSION_EXCHANGE_NOT_LIVE")
    if payload.get("symbol") != "BTCUSDT":
        blockers.append("P11_ORDER_SUBMISSION_SYMBOL_NOT_BTCUSDT")
    if str(payload.get("side") or "").upper() not in {"BUY", "SELL"}:
        blockers.append("P11_ORDER_SUBMISSION_SIDE_INVALID")
    if int(payload.get("order_count") or 0) != 1:
        blockers.append("P11_ORDER_SUBMISSION_ORDER_COUNT_NOT_ONE")
    if (_as_float(payload.get("notional_usdt"), 0) or 0) <= 0 or (_as_float(payload.get("notional_usdt"), 999) or 999) > 5:
        blockers.append("P11_ORDER_SUBMISSION_NOTIONAL_OUT_OF_CANARY_CAP")
    if (_as_float(payload.get("max_notional_usdt"), 999) or 999) > 5:
        blockers.append("P11_ORDER_SUBMISSION_MAX_NOTIONAL_OUT_OF_POLICY")
    for key, reason in (
        ("exchange_order_id", "P11_EXCHANGE_ORDER_ID_MISSING"),
        ("client_order_id", "P11_CLIENT_ORDER_ID_MISSING"),
        ("idempotency_key", "P11_IDEMPOTENCY_KEY_MISSING"),
        ("execution_id", "P11_EXECUTION_ID_MISSING"),
        ("order_intent_id", "P11_ORDER_INTENT_ID_MISSING"),
        ("risk_gate_id", "P11_RISK_GATE_ID_MISSING"),
        ("exchange_response_hash", "P11_EXCHANGE_RESPONSE_HASH_MISSING"),
        ("request_hash", "P11_REQUEST_HASH_MISSING"),
        ("response_hash", "P11_RESPONSE_HASH_MISSING"),
    ):
        if not _nonempty(payload.get(key)):
            blockers.append(reason)
    for key, reason in (
        ("actual_live_order_submitted", "P11_ACTUAL_LIVE_ORDER_SUBMISSION_EVIDENCE_MISSING"),
        ("live_order_endpoint_called", "P11_LIVE_ORDER_ENDPOINT_CALL_EVIDENCE_MISSING"),
        ("order_endpoint_called", "P11_ORDER_ENDPOINT_CALL_EVIDENCE_MISSING"),
        ("http_request_sent", "P11_HTTP_REQUEST_SENT_EVIDENCE_MISSING"),
        ("signature_created", "P11_SIGNATURE_CREATED_EVIDENCE_MISSING"),
        ("signed_request_created", "P11_SIGNED_REQUEST_EVIDENCE_MISSING"),
        ("real_exchange_response", "P11_REAL_EXCHANGE_RESPONSE_NOT_CONFIRMED"),
    ):
        if payload.get(key) is not True:
            blockers.append(reason)
    if payload.get("submitted_by_this_module") is True:
        blockers.append("P11_SUBMISSION_BY_THIS_MODULE_NOT_ALLOWED")
    for key, reason in (
        ("secret_value_included", "P11_SECRET_VALUE_INCLUDED_IN_SUBMISSION_EVIDENCE"),
        ("api_key_value_included", "P11_API_KEY_VALUE_INCLUDED_IN_SUBMISSION_EVIDENCE"),
        ("api_secret_value_included", "P11_API_SECRET_VALUE_INCLUDED_IN_SUBMISSION_EVIDENCE"),
        ("private_key_included", "P11_PRIVATE_KEY_INCLUDED_IN_SUBMISSION_EVIDENCE"),
        ("passphrase_included", "P11_PASSPHRASE_INCLUDED_IN_SUBMISSION_EVIDENCE"),
        ("secret_value_logged", "P11_SECRET_VALUE_LOGGED_IN_SUBMISSION_EVIDENCE"),
        ("mainnet_key_scope_allowed", "P11_MAINNET_KEY_SCOPE_NOT_ALLOWED"),
        ("withdrawal_permission_allowed", "P11_WITHDRAWAL_PERMISSION_NOT_ALLOWED"),
        ("transfer_permission_allowed", "P11_TRANSFER_PERMISSION_NOT_ALLOWED"),
        ("admin_permission_allowed", "P11_ADMIN_PERMISSION_NOT_ALLOWED"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    validation = {
        "live_canary_order_submission_evidence_valid": not blockers,
        "live_canary_order_submission_block_reasons": sorted(dict.fromkeys(blockers)),
        "exchange_order_id": payload.get("exchange_order_id"),
        "client_order_id": payload.get("client_order_id"),
        "idempotency_key": payload.get("idempotency_key"),
        "source_p10_live_canary_boundary_sha256": payload.get("source_p10_live_canary_boundary_sha256"),
        "expected_p10_live_canary_boundary_sha256": expected_p10_sha256,
    }
    validation["live_canary_order_submission_validation_sha256"] = sha256_json(validation)
    return validation


def validate_live_canary_status_polling_evidence(
    events: Sequence[Mapping[str, Any] | LiveCanaryStatusPollingEvidence] | None,
    *,
    exchange_order_id: str | None = None,
) -> dict[str, Any]:
    payloads = [event.to_dict() if isinstance(event, LiveCanaryStatusPollingEvidence) else dict(event or {}) for event in list(events or [])]
    blockers: list[str] = []
    if not payloads:
        blockers.append("P11_STATUS_POLLING_EVENTS_MISSING")
    statuses: list[str] = []
    for index, event in enumerate(payloads):
        prefix = f"P11_STATUS_EVENT_{index}"
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
            if not _nonempty(event.get(key)):
                blockers.append(reason)
        for key, reason in (
            ("live_order_status_endpoint_called", f"{prefix}_LIVE_ORDER_STATUS_ENDPOINT_CALL_MISSING"),
            ("order_status_endpoint_called", f"{prefix}_ORDER_STATUS_ENDPOINT_CALL_MISSING"),
            ("http_request_sent", f"{prefix}_HTTP_REQUEST_SENT_MISSING"),
            ("signature_created", f"{prefix}_SIGNATURE_CREATED_EVIDENCE_MISSING"),
            ("signed_request_created", f"{prefix}_SIGNED_REQUEST_EVIDENCE_MISSING"),
            ("real_exchange_response", f"{prefix}_REAL_EXCHANGE_RESPONSE_NOT_CONFIRMED"),
        ):
            if event.get(key) is not True:
                blockers.append(reason)
        for key, reason in (
            ("secret_value_logged", f"{prefix}_SECRET_VALUE_LOGGED"),
            ("api_key_value_logged", f"{prefix}_API_KEY_VALUE_LOGGED"),
            ("api_secret_value_logged", f"{prefix}_API_SECRET_VALUE_LOGGED"),
        ):
            if event.get(key) is True:
                blockers.append(reason)
        retry_count = int(event.get("retry_count", 0) or 0)
        if retry_count < 0 or retry_count > 3:
            blockers.append(f"{prefix}_RETRY_COUNT_OUT_OF_POLICY")
    final_status = statuses[-1] if statuses else None
    validation = {
        "live_canary_status_polling_evidence_valid": not blockers,
        "live_canary_status_polling_block_reasons": sorted(dict.fromkeys(blockers)),
        "status_polling_event_count": len(payloads),
        "status_sequence": statuses,
        "final_exchange_order_status": final_status,
        "terminal_status_observed": final_status in _TERMINAL_STATUSES,
        "status_endpoint_called": any(event.get("order_status_endpoint_called") is True for event in payloads),
        "live_order_status_endpoint_called": any(event.get("live_order_status_endpoint_called") is True for event in payloads),
    }
    validation["live_canary_status_polling_validation_sha256"] = sha256_json(validation)
    return validation


def validate_live_canary_cancel_boundary_evidence(
    evidence: Mapping[str, Any] | LiveCanaryCancelBoundaryEvidence | None,
    *,
    exchange_order_id: str | None = None,
    final_status: str | None = None,
) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, LiveCanaryCancelBoundaryEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P11_CANCEL_BOUNDARY_EVIDENCE_MISSING")
    if payload.get("cancel_boundary_decision_recorded") is not True:
        blockers.append("P11_CANCEL_BOUNDARY_DECISION_NOT_RECORDED")
    if exchange_order_id and payload.get("exchange_order_id") != exchange_order_id:
        blockers.append("P11_CANCEL_BOUNDARY_EXCHANGE_ORDER_ID_MISMATCH")
    observed = str(final_status or payload.get("final_status_before_cancel_decision") or "").upper()
    cancel_required = observed in _OPEN_STATUSES
    if cancel_required and payload.get("cancel_required") is not True:
        blockers.append("P11_CANCEL_REQUIRED_FOR_OPEN_STATUS_NOT_MARKED")
    if cancel_required and payload.get("cancel_requested") is not True:
        blockers.append("P11_CANCEL_REQUIRED_BUT_NOT_REQUESTED")
    if cancel_required and payload.get("cancel_requested") is True:
        if payload.get("live_cancel_endpoint_called") is not True or payload.get("cancel_endpoint_called") is not True or payload.get("cancel_request_sent") is not True:
            blockers.append("P11_CANCEL_REQUESTED_WITHOUT_ENDPOINT_EVIDENCE")
        if not _nonempty(payload.get("cancel_response_hash")):
            blockers.append("P11_CANCEL_RESPONSE_HASH_MISSING")
    if not cancel_required and (payload.get("cancel_endpoint_called") is True or payload.get("live_cancel_endpoint_called") is True):
        blockers.append("P11_CANCEL_ENDPOINT_CALLED_FOR_TERMINAL_STATUS")
    if payload.get("duplicate_cancel_prevented") is not True:
        blockers.append("P11_DUPLICATE_CANCEL_NOT_PREVENTED")
    for key, reason in (
        ("secret_value_logged", "P11_CANCEL_BOUNDARY_SECRET_VALUE_LOGGED"),
        ("api_key_value_logged", "P11_CANCEL_BOUNDARY_API_KEY_VALUE_LOGGED"),
        ("api_secret_value_logged", "P11_CANCEL_BOUNDARY_API_SECRET_VALUE_LOGGED"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    validation = {
        "live_canary_cancel_boundary_evidence_valid": not blockers,
        "live_canary_cancel_boundary_block_reasons": sorted(dict.fromkeys(blockers)),
        "cancel_required": cancel_required,
        "cancel_endpoint_called": payload.get("cancel_endpoint_called") is True,
        "live_cancel_endpoint_called": payload.get("live_cancel_endpoint_called") is True,
        "cancel_requested": payload.get("cancel_requested") is True,
    }
    validation["live_canary_cancel_boundary_validation_sha256"] = sha256_json(validation)
    return validation


def validate_live_canary_reconciliation_evidence(
    evidence: Mapping[str, Any] | LiveCanaryReconciliationEvidence | None,
    *,
    exchange_order_id: str | None = None,
    final_status: str | None = None,
) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, LiveCanaryReconciliationEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P11_LIVE_CANARY_RECONCILIATION_EVIDENCE_MISSING")
    if exchange_order_id and payload.get("exchange_order_id") != exchange_order_id:
        blockers.append("P11_RECONCILIATION_EXCHANGE_ORDER_ID_MISMATCH")
    if final_status and payload.get("final_exchange_order_status") != final_status:
        blockers.append("P11_RECONCILIATION_FINAL_STATUS_MISMATCH")
    for key, reason in (
        ("live_canary_reconciliation_id", "P11_LIVE_CANARY_RECONCILIATION_ID_MISSING"),
        ("client_order_id", "P11_RECONCILIATION_CLIENT_ORDER_ID_MISSING"),
        ("idempotency_key", "P11_RECONCILIATION_IDEMPOTENCY_KEY_MISSING"),
        ("execution_id", "P11_RECONCILIATION_EXECUTION_ID_MISSING"),
        ("order_intent_id", "P11_RECONCILIATION_ORDER_INTENT_ID_MISSING"),
        ("risk_gate_id", "P11_RECONCILIATION_RISK_GATE_ID_MISSING"),
    ):
        if not _nonempty(payload.get(key)):
            blockers.append(reason)
    for key, reason in (
        ("submitted_to_exchange", "P11_RECONCILIATION_SUBMISSION_NOT_CONFIRMED"),
        ("exchange_response_hash_match", "P11_EXCHANGE_RESPONSE_HASH_MISMATCH"),
        ("status_polling_hash_chain_match", "P11_STATUS_POLLING_HASH_CHAIN_MISMATCH"),
        ("order_intent_match", "P11_ORDER_INTENT_MISMATCH"),
        ("idempotency_key_match", "P11_IDEMPOTENCY_KEY_MISMATCH"),
        ("fee_reconciled", "P11_FEE_NOT_RECONCILED"),
        ("fill_quantity_reconciled", "P11_FILL_QUANTITY_NOT_RECONCILED"),
        ("position_delta_reconciled", "P11_POSITION_DELTA_NOT_RECONCILED"),
        ("slippage_recorded", "P11_SLIPPAGE_NOT_RECORDED"),
    ):
        if payload.get(key) is not True:
            blockers.append(reason)
    if int(payload.get("reconciliation_mismatch_count") or 0) != 0:
        blockers.append("P11_RECONCILIATION_MISMATCH_COUNT_NONZERO")
    if int(payload.get("api_error_count") or 0) != 0:
        blockers.append("P11_API_ERROR_COUNT_NONZERO")
    if int(payload.get("manual_override_count") or 0) != 0:
        blockers.append("P11_MANUAL_OVERRIDE_COUNT_NONZERO")
    if _bool(payload.get("duplicate_submit_detected")):
        blockers.append("P11_DUPLICATE_SUBMIT_DETECTED")
    if _bool(payload.get("unintended_second_order_detected")):
        blockers.append("P11_UNINTENDED_SECOND_ORDER_DETECTED")
    if (_as_float(payload.get("paper_live_gap"), 0) or 0) > 0.5:
        blockers.append("P11_PAPER_LIVE_GAP_TOO_HIGH")
    if (_as_float(payload.get("slippage_bps"), 0) or 0) > 10:
        blockers.append("P11_SLIPPAGE_BPS_TOO_HIGH")
    if (_as_float(payload.get("latency_ms"), 0) or 0) > 3000:
        blockers.append("P11_LATENCY_MS_TOO_HIGH")
    for key, reason in (
        ("secret_value_logged", "P11_RECONCILIATION_SECRET_VALUE_LOGGED"),
        ("external_position_sync_performed_by_this_module", "P11_RECONCILIATION_EXTERNAL_POSITION_SYNC_BY_THIS_MODULE"),
        ("live_trading_allowed_by_this_module", "P11_RECONCILIATION_LIVE_TRADING_ALLOWED_BY_THIS_MODULE"),
        ("live_scaled_promotion_allowed", "P11_RECONCILIATION_LIVE_SCALED_PROMOTION_ATTEMPT"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    validation = {
        "live_canary_reconciliation_evidence_valid": not blockers,
        "live_canary_reconciliation_block_reasons": sorted(dict.fromkeys(blockers)),
        "live_canary_reconciliation_id": payload.get("live_canary_reconciliation_id"),
        "reconciliation_mismatch_count": int(payload.get("reconciliation_mismatch_count") or 0) if payload else None,
        "api_error_count": int(payload.get("api_error_count") or 0) if payload else None,
        "slippage_bps": _as_float(payload.get("slippage_bps"), 0) if payload else None,
        "latency_ms": _as_float(payload.get("latency_ms"), 0) if payload else None,
    }
    validation["live_canary_reconciliation_validation_sha256"] = sha256_json(validation)
    return validation


def validate_live_canary_outcome_review_evidence(
    evidence: Mapping[str, Any] | LiveCanaryOutcomeReviewEvidence | None,
    *,
    reconciliation_id: str | None = None,
) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, LiveCanaryOutcomeReviewEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P11_LIVE_CANARY_OUTCOME_REVIEW_EVIDENCE_MISSING")
    if reconciliation_id and payload.get("live_canary_reconciliation_id") != reconciliation_id:
        blockers.append("P11_OUTCOME_REVIEW_RECONCILIATION_ID_MISMATCH")
    if not _nonempty(payload.get("canary_outcome_report_id")):
        blockers.append("P11_CANARY_OUTCOME_REPORT_ID_MISSING")
    for key, reason in (
        ("outcome_review_completed", "P11_OUTCOME_REVIEW_NOT_COMPLETED"),
        ("canary_outcome_clean", "P11_CANARY_OUTCOME_NOT_CLEAN"),
        ("post_submit_relock_confirmed", "P11_POST_SUBMIT_RELOCK_NOT_CONFIRMED"),
        ("monitoring_alerting_ready", "P11_MONITORING_ALERTING_NOT_READY"),
        ("deployment_runbook_ready", "P11_DEPLOYMENT_RUNBOOK_NOT_READY"),
        ("rollback_runbook_ready", "P11_ROLLBACK_RUNBOOK_NOT_READY"),
        ("kill_switch_rechecked_after_submit", "P11_KILL_SWITCH_NOT_RECHECKED_AFTER_SUBMIT"),
        ("slippage_within_threshold", "P11_SLIPPAGE_OUTSIDE_THRESHOLD"),
        ("latency_within_threshold", "P11_LATENCY_OUTSIDE_THRESHOLD"),
        ("api_error_rate_within_threshold", "P11_API_ERROR_RATE_OUTSIDE_THRESHOLD"),
        ("rejection_rate_within_threshold", "P11_REJECTION_RATE_OUTSIDE_THRESHOLD"),
    ):
        if payload.get(key) is not True:
            blockers.append(reason)
    if int(payload.get("monitoring_critical_alert_count") or 0) != 0:
        blockers.append("P11_MONITORING_CRITICAL_ALERT_COUNT_NONZERO")
    for key, reason in (
        ("manual_kill_switch_active_after_submit", "P11_MANUAL_KILL_SWITCH_ACTIVE_AFTER_SUBMIT"),
        ("incident_required", "P11_INCIDENT_REQUIRED"),
        ("live_scaled_readiness_candidate_created", "P11_LIVE_SCALED_READINESS_CANDIDATE_CREATED_TOO_EARLY"),
        ("live_scaled_promotion_allowed", "P11_LIVE_SCALED_PROMOTION_ALLOWED_TOO_EARLY"),
        ("live_scaled_execution_enabled", "P11_LIVE_SCALED_EXECUTION_ENABLED"),
        ("runtime_settings_mutated", "P11_RUNTIME_SETTINGS_MUTATED"),
        ("score_weights_mutated", "P11_SCORE_WEIGHTS_MUTATED"),
        ("auto_promotion_allowed", "P11_AUTO_PROMOTION_ALLOWED"),
        ("secret_value_accessed", "P11_OUTCOME_SECRET_VALUE_ACCESSED"),
        ("secret_value_logged", "P11_OUTCOME_SECRET_VALUE_LOGGED"),
    ):
        if payload.get(key) is True:
            blockers.append(reason)
    validation = {
        "live_canary_outcome_review_evidence_valid": not blockers,
        "live_canary_outcome_review_block_reasons": sorted(dict.fromkeys(blockers)),
        "canary_outcome_report_id": payload.get("canary_outcome_report_id"),
        "post_submit_relock_confirmed": payload.get("post_submit_relock_confirmed") is True,
        "monitoring_critical_alert_count": int(payload.get("monitoring_critical_alert_count") or 0) if payload else None,
    }
    validation["live_canary_outcome_review_validation_sha256"] = sha256_json(validation)
    return validation


def build_p11_live_canary_post_submit_evidence_review_report(
    *,
    cfg: AppConfig | None = None,
    p10_report: Mapping[str, Any] | None = None,
    order_submission: Mapping[str, Any] | LiveCanaryOrderSubmissionEvidence | None = None,
    status_polling_events: Sequence[Mapping[str, Any] | LiveCanaryStatusPollingEvidence] | None = None,
    cancel_boundary: Mapping[str, Any] | LiveCanaryCancelBoundaryEvidence | None = None,
    reconciliation_evidence: Mapping[str, Any] | LiveCanaryReconciliationEvidence | None = None,
    outcome_review_evidence: Mapping[str, Any] | LiveCanaryOutcomeReviewEvidence | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    source_p10 = dict(p10_report or _read_latest_json(cfg, "p10_live_canary_one_order_execution_boundary_report.json"))
    source_p10_sha256 = _sha_from(source_p10, "p10_live_canary_one_order_execution_boundary_sha256", "p10_summary_sha256", "report_sha256")
    p10_ready, p10_blockers = _p10_boundary_state(source_p10)

    if not order_submission:
        unsafe_p10_wait_blockers = [
            reason for reason in p10_blockers
            if reason not in {
                "P11_BLOCK_P10_LIVE_CANARY_EXECUTION_BOUNDARY_MISSING",
                "P11_BLOCK_P10_LIVE_CANARY_EXECUTION_BOUNDARY_NOT_READY",
            }
        ]
        report = {
            "artifact_type": "p11_live_canary_post_submit_evidence_review",
            "p11_live_canary_post_submit_evidence_review_version": P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_VERSION,
            "status": STATUS_WAITING_REVIEW_ONLY if not unsafe_p10_wait_blockers else STATUS_BLOCKED_FAIL_CLOSED,
            "blocked": bool(unsafe_p10_wait_blockers),
            "fail_closed": bool(unsafe_p10_wait_blockers),
            "review_only": True,
            "source_p10_live_canary_boundary_present": bool(source_p10),
            "source_p10_live_canary_boundary_status": source_p10.get("status"),
            "source_p10_live_canary_boundary_sha256": source_p10_sha256,
            "external_live_canary_submit_evidence_present": False,
            "live_canary_post_submit_chain_complete": False,
            "live_canary_reconciliation_clean": False,
            "canary_outcome_review_completed": False,
            "post_submit_relock_confirmed": False,
            "next_required_action": "WAIT_FOR_SEPARATELY_APPROVED_EXTERNAL_LIVE_CANARY_ORDER_SUBMISSION_EVIDENCE",
            "block_reasons": sorted(dict.fromkeys(unsafe_p10_wait_blockers)),
            "created_at_utc": created_at_utc,
            **_disabled_payload(),
        }
        report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
        if report["unsafe_truthy_execution_flags"]:
            report["status"] = STATUS_BLOCKED_FAIL_CLOSED
            report["blocked"] = True
            report["fail_closed"] = True
            report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P11_UNSAFE_TRUTHY_EXECUTION_FLAGS_IN_WAITING_STATE"]))
        report["p11_live_canary_post_submit_evidence_review_id"] = stable_id("p11_live_canary_post_submit_evidence_review", report, 24)
        report["p11_live_canary_post_submit_evidence_review_sha256"] = sha256_json(report)
        return report

    order_validation = validate_live_canary_order_submission_evidence(order_submission, expected_p10_sha256=source_p10_sha256)
    exchange_order_id = str(order_validation.get("exchange_order_id") or "")
    status_validation = validate_live_canary_status_polling_evidence(status_polling_events, exchange_order_id=exchange_order_id)
    final_status = str(status_validation.get("final_exchange_order_status") or "")
    cancel_validation = validate_live_canary_cancel_boundary_evidence(cancel_boundary, exchange_order_id=exchange_order_id, final_status=final_status)
    reconciliation_validation = validate_live_canary_reconciliation_evidence(reconciliation_evidence, exchange_order_id=exchange_order_id, final_status=final_status)
    reconciliation_id = str(reconciliation_validation.get("live_canary_reconciliation_id") or "")
    outcome_validation = validate_live_canary_outcome_review_evidence(outcome_review_evidence, reconciliation_id=reconciliation_id)

    blockers = sorted(
        dict.fromkeys(
            p10_blockers
            + list(order_validation["live_canary_order_submission_block_reasons"])
            + list(status_validation["live_canary_status_polling_block_reasons"])
            + list(cancel_validation["live_canary_cancel_boundary_block_reasons"])
            + list(reconciliation_validation["live_canary_reconciliation_block_reasons"])
            + list(outcome_validation["live_canary_outcome_review_block_reasons"])
        )
    )
    chain_complete = bool(
        p10_ready
        and order_validation["live_canary_order_submission_evidence_valid"]
        and status_validation["live_canary_status_polling_evidence_valid"]
        and cancel_validation["live_canary_cancel_boundary_evidence_valid"]
        and reconciliation_validation["live_canary_reconciliation_evidence_valid"]
        and outcome_validation["live_canary_outcome_review_evidence_valid"]
        and not blockers
    )
    status = STATUS_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY if chain_complete else STATUS_BLOCKED_FAIL_CLOSED
    report = {
        "artifact_type": "p11_live_canary_post_submit_evidence_review",
        "p11_live_canary_post_submit_evidence_review_version": P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "source_p10_live_canary_boundary_present": bool(source_p10),
        "source_p10_live_canary_boundary_status": source_p10.get("status"),
        "source_p10_live_canary_boundary_sha256": source_p10_sha256,
        "external_live_canary_submit_evidence_present": True,
        "live_canary_post_submit_chain_complete": chain_complete,
        "live_canary_order_submission_validation": order_validation,
        "live_canary_status_polling_validation": status_validation,
        "live_canary_cancel_boundary_validation": cancel_validation,
        "live_canary_reconciliation_validation": reconciliation_validation,
        "live_canary_outcome_review_validation": outcome_validation,
        "final_exchange_order_status": final_status,
        "terminal_status_observed": status_validation["terminal_status_observed"],
        "live_canary_reconciliation_clean": reconciliation_validation["live_canary_reconciliation_evidence_valid"],
        "canary_outcome_review_completed": outcome_validation["live_canary_outcome_review_evidence_valid"],
        "post_submit_relock_confirmed": outcome_validation["post_submit_relock_confirmed"],
        "live_canary_order_evidence_exists": True,
        "live_canary_order_count": 1 if chain_complete else None,
        "live_canary_no_unintended_second_order": chain_complete,
        "live_canary_slippage_latency_api_error_within_threshold": chain_complete,
        "live_canary_secret_leak_absent": chain_complete,
        "live_canary_outcome_review_clean": chain_complete,
        "live_scaled_readiness_candidate_created": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_canary_execution_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "block_reasons": blockers,
        "created_at_utc": created_at_utc,
        **_disabled_payload(
            external_live_submit_performed=True,
            status_endpoint_called=status_validation["status_endpoint_called"],
            cancel_endpoint_called=cancel_validation["cancel_endpoint_called"],
        ),
    }
    report["unsafe_truthy_execution_flags"] = [] if chain_complete else truthy_execution_flags(report)
    if not chain_complete and report["unsafe_truthy_execution_flags"]:
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P11_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p11_live_canary_post_submit_evidence_review_id"] = stable_id("p11_live_canary_post_submit_evidence_review", report, 24)
    report["p11_live_canary_post_submit_evidence_review_sha256"] = sha256_json(report)
    return report


def build_valid_p11_fixture_sources() -> dict[str, Any]:
    p10_sources = build_valid_p10_fixture_sources()
    p10_report = build_p10_live_canary_one_order_execution_boundary_report(**p10_sources)
    p10_hash = p10_report["p10_live_canary_one_order_execution_boundary_sha256"]
    return {
        "p10_report": p10_report,
        "order_submission": LiveCanaryOrderSubmissionEvidence(source_p10_live_canary_boundary_sha256=p10_hash),
        "status_polling_events": [LiveCanaryStatusPollingEvidence()],
        "cancel_boundary": LiveCanaryCancelBoundaryEvidence(),
        "reconciliation_evidence": LiveCanaryReconciliationEvidence(),
        "outcome_review_evidence": LiveCanaryOutcomeReviewEvidence(),
    }


def build_p11_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = build_valid_p11_fixture_sources()
    cases: dict[str, dict[str, Any]] = {
        "missing_exchange_order_id": {"order_submission": {**valid["order_submission"].to_dict(), "exchange_order_id": ""}},
        "p10_hash_mismatch": {"order_submission": {**valid["order_submission"].to_dict(), "source_p10_live_canary_boundary_sha256": "9" * 64}},
        "status_polling_secret_leak": {"status_polling_events": [{**LiveCanaryStatusPollingEvidence().to_dict(), "secret_value_logged": True}]},
        "cancel_required_without_request": {
            "status_polling_events": [{**LiveCanaryStatusPollingEvidence().to_dict(), "exchange_order_status": "NEW"}],
            "cancel_boundary": {**LiveCanaryCancelBoundaryEvidence().to_dict(), "final_status_before_cancel_decision": "NEW", "cancel_required": True, "cancel_requested": False},
            "reconciliation_evidence": {**LiveCanaryReconciliationEvidence().to_dict(), "final_exchange_order_status": "NEW"},
        },
        "reconciliation_mismatch": {"reconciliation_evidence": {**LiveCanaryReconciliationEvidence().to_dict(), "reconciliation_mismatch_count": 1}},
        "unintended_second_order": {"reconciliation_evidence": {**LiveCanaryReconciliationEvidence().to_dict(), "unintended_second_order_detected": True}},
        "outcome_critical_alert": {"outcome_review_evidence": {**LiveCanaryOutcomeReviewEvidence().to_dict(), "monitoring_critical_alert_count": 1}},
        "post_submit_relock_missing": {"outcome_review_evidence": {**LiveCanaryOutcomeReviewEvidence().to_dict(), "post_submit_relock_confirmed": False}},
        "live_scaled_promotion_attempt": {"outcome_review_evidence": {**LiveCanaryOutcomeReviewEvidence().to_dict(), "live_scaled_promotion_allowed": True}},
        "secret_in_submission_evidence": {"order_submission": {**valid["order_submission"].to_dict(), "secret_value_included": True}},
        "submission_by_this_module": {"order_submission": {**valid["order_submission"].to_dict(), "submitted_by_this_module": True}},
    }
    results: dict[str, Any] = {}
    for name, patch in cases.items():
        sources = dict(valid)
        sources.update(patch)
        report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg, **sources)
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "live_scaled_execution_enabled": False,
            "live_scaled_promotion_allowed": False,
            "secret_value_accessed": False,
        }
    payload = {
        "artifact_type": "p11_live_canary_post_submit_evidence_review_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_scaled_promotion_allowed": False,
        "secret_value_accessed": False,
        **_disabled_payload(),
    }
    payload["p11_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p11_live_canary_post_submit_evidence_review(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_p11_live_canary_post_submit_evidence_review_report(cfg=cfg)
    negative = build_p11_negative_fixture_results(cfg=cfg)
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p11_live_canary_post_submit_evidence_review")
    registry_record = append_registry_record(
        registry_path(cfg, P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_REGISTRY_NAME),
        {
            "artifact_type": "p11_live_canary_post_submit_evidence_review_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "p11_live_canary_post_submit_evidence_review_id": report["p11_live_canary_post_submit_evidence_review_id"],
            "p11_live_canary_post_submit_evidence_review_sha256": report["p11_live_canary_post_submit_evidence_review_sha256"],
            "external_live_canary_submit_evidence_present": report["external_live_canary_submit_evidence_present"],
            "live_canary_post_submit_chain_complete": report["live_canary_post_submit_chain_complete"],
            "live_scaled_execution_enabled": False,
            "live_scaled_promotion_allowed": False,
            "secret_value_accessed": False,
            "created_at_utc": utc_now_canonical(),
        },
        registry_name=P11_LIVE_CANARY_POST_SUBMIT_EVIDENCE_REVIEW_REGISTRY_NAME,
        id_field="p11_live_canary_post_submit_evidence_review_registry_record_id",
        hash_field="p11_live_canary_post_submit_evidence_review_registry_record_sha256",
        id_prefix="p11_live_canary_post_submit_evidence_review_registry_record",
    )
    report["p11_live_canary_post_submit_evidence_review_registry_record_id"] = registry_record[
        "p11_live_canary_post_submit_evidence_review_registry_record_id"
    ]
    report["p11_live_canary_post_submit_evidence_review_registry_record_sha256"] = registry_record[
        "p11_live_canary_post_submit_evidence_review_registry_record_sha256"
    ]
    summary = {
        "status": report["status"],
        "blocked": report["blocked"],
        "p11_live_canary_post_submit_evidence_review_id": report["p11_live_canary_post_submit_evidence_review_id"],
        "external_live_canary_submit_evidence_present": report["external_live_canary_submit_evidence_present"],
        "live_canary_post_submit_chain_complete": report["live_canary_post_submit_chain_complete"],
        "live_canary_reconciliation_clean": report["live_canary_reconciliation_clean"],
        "canary_outcome_review_completed": report["canary_outcome_review_completed"],
        "post_submit_relock_confirmed": report["post_submit_relock_confirmed"],
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_scaled_promotion_allowed": False,
        "secret_value_accessed": False,
        "block_reasons": report["block_reasons"],
    }
    summary["p11_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p11_live_canary_post_submit_evidence_review_report.json", report)
    atomic_write_json(latest / "p11_live_canary_post_submit_evidence_review_summary.json", summary)
    atomic_write_json(latest / "p11_live_canary_post_submit_evidence_review_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p11_live_canary_post_submit_evidence_review_registry_record.json", registry_record)
    atomic_write_json(storage / "p11_live_canary_post_submit_evidence_review_report.json", report)
    return report


__all__ = [
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_OUTCOME_REVIEW_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "LiveCanaryOrderSubmissionEvidence",
    "LiveCanaryStatusPollingEvidence",
    "LiveCanaryCancelBoundaryEvidence",
    "LiveCanaryReconciliationEvidence",
    "LiveCanaryOutcomeReviewEvidence",
    "build_p11_live_canary_post_submit_evidence_review_report",
    "build_p11_negative_fixture_results",
    "build_valid_p11_fixture_sources",
    "persist_p11_live_canary_post_submit_evidence_review",
    "validate_live_canary_order_submission_evidence",
    "validate_live_canary_status_polling_evidence",
    "validate_live_canary_cancel_boundary_evidence",
    "validate_live_canary_reconciliation_evidence",
    "validate_live_canary_outcome_review_evidence",
]
