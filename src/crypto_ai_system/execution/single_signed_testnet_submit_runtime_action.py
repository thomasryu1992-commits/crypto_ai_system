from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.action_time_submit_approval_boundary import (
    EXPLICIT_APPROVAL_PHRASE as P5_EXPLICIT_APPROVAL_PHRASE,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.execution.signed_testnet_one_order_runtime_package import (
    OneOrderRuntimeIntent,
    RuntimeSecretBindingMetadata,
    validate_one_order_guard,
    validate_runtime_secret_binding_metadata,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_VERSION = "p6_single_signed_testnet_submit_runtime_action_v1"
P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_REGISTRY_NAME = "p6_single_signed_testnet_submit_runtime_action_registry"
STATUS_READY_DISABLED_NO_SUBMIT = "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_READY_DISABLED_NO_SUBMIT"
STATUS_BLOCKED_FAIL_CLOSED = "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_BLOCKED_FAIL_CLOSED"
STATUS_SUBMITTED_BY_EXTERNAL_RUNTIME = "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_SUBMITTED_BY_EXTERNAL_RUNTIME"

P6_EXPLICIT_RUNTIME_ARMING_PHRASE = "I APPROVE EXECUTING EXACTLY ONE BTCUSDT SIGNED TESTNET ORDER NOW"
_ALLOWED_RISK_GATE_RESULTS = {"PASS_SIGNED_TESTNET", "PASS_TESTNET_PRE_SUBMIT"}
_ALLOWED_ORDER_STATUSES = {"NEW", "PARTIALLY_FILLED", "FILLED", "REJECTED", "CANCELED", "EXPIRED"}

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


def _public_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "p5_action_time_submit_approval_boundary_sha256",
        "p5_summary_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _disabled_payload(*, endpoint_called: bool = False, http_request_sent: bool = False, submitted: bool = False) -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED_FLAGS)
    payload.update(
        {
            "external_order_submission_performed": submitted,
            "actual_order_submission_performed": submitted,
            "actual_testnet_order_submitted": submitted,
            "runtime_submit_action_executed": submitted,
            "runtime_submit_action_performed": submitted,
            "order_endpoint_called": endpoint_called,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "http_request_sent": http_request_sent,
            "signature_created": bool(submitted),
            "signed_request_created": bool(submitted),
            "real_exchange_order_id_present": bool(submitted),
        }
    )
    if not submitted:
        payload["signature_created"] = False
        payload["signed_request_created"] = False
        payload["external_order_submission_performed"] = False
        payload["actual_order_submission_performed"] = False
        payload["actual_testnet_order_submitted"] = False
        payload["runtime_submit_action_executed"] = False
        payload["runtime_submit_action_performed"] = False
        payload["real_exchange_order_id_present"] = False
    return payload


class SignedTestnetSubmitAdapter(Protocol):
    adapter_id: str
    venue: str
    environment: str
    real_endpoint_adapter: bool

    def place_order(self, *, intent: OneOrderRuntimeIntent, idempotency_key: str, secret_reference_id: str) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class SingleSignedTestnetRuntimeArmingEvidence:
    operator_id: str = "operator_thomas_local_runtime_fixture"
    approval_ticket_id: str = "ticket_signed_testnet_runtime_action_1"
    explicit_runtime_arming_text: str = P6_EXPLICIT_RUNTIME_ARMING_PHRASE
    source_p5_action_time_boundary_sha256: str | None = None
    local_console_confirmed: bool = True
    human_operator_submitted: bool = True
    testnet_only: bool = True
    btcusdt_only: bool = True
    max_order_count: int = 1
    low_notional_cap_confirmed: bool = True
    no_auto_generated_runtime_approval_file: bool = True
    understands_real_order_endpoint_may_be_called_when_armed: bool = True
    runtime_network_call_allowed_by_operator: bool = False
    execute_real_submit_now: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["explicit_runtime_arming_phrase_expected"] = P6_EXPLICIT_RUNTIME_ARMING_PHRASE
        payload["p5_explicit_approval_phrase_reference"] = P5_EXPLICIT_APPROVAL_PHRASE
        payload["runtime_arming_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class SingleSignedTestnetRuntimeFreshnessEvidence:
    action_time_boundary_age_sec: int = 10
    endpoint_time_sync_age_ms: int = 250
    hot_path_preorder_risk_gate_age_sec: int = 5
    hot_path_preorder_risk_gate_result: str = "PASS_SIGNED_TESTNET"
    hot_path_preorder_risk_gate_id: str = "risk_gate_signed_testnet_runtime_submit_1"
    duplicate_submit_lock_acquired: bool = True
    idempotency_key_already_seen: bool = False
    post_submit_relock_ready: bool = True
    manual_kill_switch_confirmed_safe: bool = True
    config_kill_switch_enabled: bool = False
    daily_loss_cap_within_limit: bool = True
    consecutive_loss_cap_within_limit: bool = True
    api_error_rate_within_limit: bool = True
    reconciliation_mismatch_within_limit: bool = True
    stale_data_kill_switch_active: bool = False
    hard_required_price_source_missing: bool = False
    venue_testnet_ready: bool = True
    adapter_symbol_filter_passed: bool = True
    monitoring_evidence_sink_ready: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runtime_freshness_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class RedactedExchangeSubmitEvidence:
    endpoint_type: str
    method: str
    request_hash: str
    response_hash: str | None
    timestamp_utc: str
    idempotency_key: str
    retry_count: int
    rate_limit_status: str
    order_endpoint_called: bool
    http_request_sent: bool
    signature_created: bool
    signed_request_created: bool
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False
    blocked_before_http: bool = False
    exchange_order_id: str | None = None
    exchange_order_status: str | None = None
    real_exchange_response: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["endpoint_submit_evidence_sha256"] = sha256_json(payload)
        return payload




@dataclass(frozen=True)
class SignedTestnetAdapterBoundaryEvidence:
    """Review-safe adapter boundary declaration for the external P6 runtime.

    This object deliberately records only interface metadata. It must never carry
    API key values, API secret values, private keys, request signatures, or raw
    endpoint payloads.
    """

    adapter_id: str = "disabled_by_default_signed_testnet_submit_adapter_v1"
    adapter_family: str = "disabled_default_no_submit"
    venue: str = "binance_futures_testnet"
    environment: str = "testnet"
    symbol_scope: str = "BTCUSDT_ONLY"
    branch_or_package_scope: str = "review_package_default_no_submit"
    real_endpoint_adapter: bool = False
    network_call_capable: bool = False
    can_submit_orders_by_default: bool = False
    code_path_isolated_from_review_package: bool = True
    external_runtime_only: bool = True
    disabled_adapter_available: bool = True
    order_endpoint_path_ref: str = "TESTNET_ORDER_ENDPOINT_PATH_REF_ONLY"
    status_endpoint_path_ref: str = "TESTNET_STATUS_ENDPOINT_PATH_REF_ONLY"
    cancel_endpoint_path_ref: str = "TESTNET_CANCEL_ENDPOINT_PATH_REF_ONLY"
    request_signing_location: str = "external_runtime_process_memory_only"
    secret_values_accepted_by_report: bool = False
    secret_values_logged_by_adapter: bool = False
    supports_idempotency_key: bool = True
    supports_duplicate_submit_lock: bool = True
    supports_post_submit_relock: bool = True
    supports_redacted_evidence_export: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["adapter_boundary_evidence_sha256"] = sha256_json(payload)
        return payload


def _adapter_boundary_from_adapter(adapter: Any, *, submit_requested: bool) -> dict[str, Any]:
    real_endpoint_adapter = getattr(adapter, "real_endpoint_adapter", False) is True
    boundary = SignedTestnetAdapterBoundaryEvidence(
        adapter_id=str(getattr(adapter, "adapter_id", "unknown_adapter")),
        adapter_family="real_endpoint_external_runtime" if real_endpoint_adapter else "disabled_default_no_submit",
        venue=str(getattr(adapter, "venue", "unknown")),
        environment=str(getattr(adapter, "environment", "unknown")),
        branch_or_package_scope="separate_local_runtime_package_required" if real_endpoint_adapter else "review_package_default_no_submit",
        real_endpoint_adapter=real_endpoint_adapter,
        network_call_capable=bool(real_endpoint_adapter and submit_requested),
        can_submit_orders_by_default=False,
    ).to_dict()
    return boundary


def validate_signed_testnet_adapter_boundary(
    evidence: Mapping[str, Any] | SignedTestnetAdapterBoundaryEvidence | None,
    *,
    submit_requested: bool,
) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, SignedTestnetAdapterBoundaryEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not _is_nonempty(payload.get("adapter_id")):
        blockers.append("P6_ADAPTER_ID_MISSING")
    if payload.get("environment") != "testnet":
        blockers.append("P6_ADAPTER_ENVIRONMENT_NOT_TESTNET")
    if str(payload.get("venue") or "").lower().find("testnet") < 0:
        blockers.append("P6_ADAPTER_VENUE_NOT_TESTNET_SCOPED")
    if payload.get("symbol_scope") != "BTCUSDT_ONLY":
        blockers.append("P6_ADAPTER_SYMBOL_SCOPE_NOT_BTCUSDT_ONLY")
    if payload.get("can_submit_orders_by_default") is not False:
        blockers.append("P6_ADAPTER_CAN_SUBMIT_BY_DEFAULT")
    if payload.get("code_path_isolated_from_review_package") is not True:
        blockers.append("P6_ADAPTER_CODE_PATH_NOT_ISOLATED")
    if payload.get("external_runtime_only") is not True:
        blockers.append("P6_ADAPTER_NOT_EXTERNAL_RUNTIME_ONLY")
    if payload.get("disabled_adapter_available") is not True:
        blockers.append("P6_DISABLED_ADAPTER_NOT_AVAILABLE")
    if payload.get("request_signing_location") != "external_runtime_process_memory_only":
        blockers.append("P6_REQUEST_SIGNING_LOCATION_NOT_PROCESS_MEMORY_ONLY")
    if payload.get("secret_values_accepted_by_report") is not False:
        blockers.append("P6_ADAPTER_REPORT_ACCEPTS_SECRET_VALUES")
    if payload.get("secret_values_logged_by_adapter") is True:
        blockers.append("P6_ADAPTER_LOGS_SECRET_VALUES")
    for key, reason in (
        ("supports_idempotency_key", "P6_ADAPTER_IDEMPOTENCY_NOT_SUPPORTED"),
        ("supports_duplicate_submit_lock", "P6_ADAPTER_DUPLICATE_LOCK_NOT_SUPPORTED"),
        ("supports_post_submit_relock", "P6_ADAPTER_POST_SUBMIT_RELOCK_NOT_SUPPORTED"),
        ("supports_redacted_evidence_export", "P6_ADAPTER_REDACTED_EVIDENCE_EXPORT_NOT_SUPPORTED"),
    ):
        if payload.get(key) is not True:
            blockers.append(reason)
    real_adapter = payload.get("real_endpoint_adapter") is True
    network_capable = payload.get("network_call_capable") is True
    if submit_requested and not real_adapter:
        blockers.append("P6_ADAPTER_REAL_ENDPOINT_REQUIRED_FOR_SUBMIT")
    if submit_requested and not network_capable:
        blockers.append("P6_ADAPTER_NETWORK_CAPABILITY_REQUIRED_FOR_SUBMIT")
    if not submit_requested and network_capable:
        blockers.append("P6_ADAPTER_NETWORK_CAPABLE_WHILE_SUBMIT_NOT_REQUESTED")
    text_blob = " ".join(str(v).lower() for v in payload.values())
    if "mainnet" in text_blob or "live_trade" in text_blob or "withdraw" in text_blob:
        blockers.append("P6_ADAPTER_BOUNDARY_CONTAINS_LIVE_OR_WITHDRAWAL_SCOPE")
    validation = {
        "adapter_boundary_valid": not blockers,
        "adapter_boundary_block_reasons": sorted(dict.fromkeys(blockers)),
        "submit_requested": submit_requested,
        "adapter_id": payload.get("adapter_id"),
        "adapter_family": payload.get("adapter_family"),
        "venue": payload.get("venue"),
        "environment": payload.get("environment"),
        "real_endpoint_adapter": real_adapter,
        "network_call_capable": network_capable,
        "can_submit_orders_by_default": payload.get("can_submit_orders_by_default") is True,
        "external_runtime_only": payload.get("external_runtime_only") is True,
    }
    validation["adapter_boundary_validation_sha256"] = sha256_json(validation)
    return validation


def build_p6_external_runtime_preflight_report(
    *,
    p5_ok: bool,
    arming_validation: Mapping[str, Any],
    freshness_validation: Mapping[str, Any],
    secret_validation: Mapping[str, Any],
    one_order_guard: Mapping[str, Any],
    adapter_boundary_validation: Mapping[str, Any],
    submit_requested: bool,
    runtime_network_allowed: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not p5_ok:
        blockers.append("P6_PREFLIGHT_P5_NOT_READY")
    if arming_validation.get("runtime_arming_evidence_valid") is not True:
        blockers.append("P6_PREFLIGHT_ARMING_INVALID")
    if freshness_validation.get("runtime_freshness_evidence_valid") is not True:
        blockers.append("P6_PREFLIGHT_FRESHNESS_INVALID")
    if secret_validation.get("secret_binding_metadata_valid") is not True:
        blockers.append("P6_PREFLIGHT_SECRET_BINDING_METADATA_INVALID")
    if one_order_guard.get("one_order_guard_passed") is not True:
        blockers.append("P6_PREFLIGHT_ONE_ORDER_GUARD_INVALID")
    if adapter_boundary_validation.get("adapter_boundary_valid") is not True:
        blockers.append("P6_PREFLIGHT_ADAPTER_BOUNDARY_INVALID")
    if submit_requested and not runtime_network_allowed:
        blockers.append("P6_PREFLIGHT_NETWORK_ALLOWANCE_MISSING")
    status = "P6_EXTERNAL_RUNTIME_PREFLIGHT_READY_REVIEW_ONLY_NO_SUBMIT" if not blockers else "P6_EXTERNAL_RUNTIME_PREFLIGHT_BLOCKED_FAIL_CLOSED"
    payload = {
        "artifact_type": "p6_external_runtime_preflight_report",
        "p6_external_runtime_preflight_version": "p6_external_runtime_preflight_v1",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_package_default_no_submit": not submit_requested,
        "external_runtime_only": True,
        "preflight_passed": not blockers,
        "submit_requested": submit_requested,
        "runtime_network_call_allowed_by_operator": runtime_network_allowed,
        "endpoint_call_must_remain_blocked_before_all_preconditions_pass": True,
        "secret_binding_metadata_only": secret_validation.get("secret_binding_metadata_valid") is True,
        "process_memory_secret_binding_required_for_external_runtime": True,
        "redacted_evidence_export_required_after_submit": True,
        "p7_post_submit_evidence_required_after_submit": True,
        "p8_repeated_clean_sessions_required_before_live_canary": True,
        "preflight_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_validation_hashes": {
            "runtime_arming_validation_sha256": arming_validation.get("runtime_arming_validation_sha256"),
            "runtime_freshness_validation_sha256": freshness_validation.get("runtime_freshness_validation_sha256"),
            "secret_binding_validation_sha256": secret_validation.get("secret_binding_validation_sha256"),
            "one_order_guard_sha256": one_order_guard.get("one_order_guard_sha256"),
            "adapter_boundary_validation_sha256": adapter_boundary_validation.get("adapter_boundary_validation_sha256"),
        },
        **_disabled_payload(),
    }
    payload["p6_external_runtime_preflight_report_sha256"] = sha256_json(payload)
    return payload

class DisabledByDefaultSignedTestnetSubmitAdapter:
    adapter_id = "disabled_by_default_signed_testnet_submit_adapter_v1"
    venue = "binance_futures_testnet"
    environment = "testnet"
    real_endpoint_adapter = False

    def prepare_disabled_submit_evidence(self, *, intent: OneOrderRuntimeIntent, idempotency_key: str) -> dict[str, Any]:
        request_preview = {
            "symbol": intent.symbol,
            "side": intent.side,
            "type": intent.order_type,
            "quantity": intent.quantity,
            "newClientOrderId": idempotency_key,
            "timestamp": "NOT_CREATED_DISABLED_DEFAULT",
            "recvWindow": "NOT_CREATED_DISABLED_DEFAULT",
        }
        evidence = RedactedExchangeSubmitEvidence(
            endpoint_type="signed_testnet_private_place_order",
            method="POST",
            request_hash=sha256_json(request_preview),
            response_hash=None,
            timestamp_utc=utc_now_canonical(),
            idempotency_key=idempotency_key,
            retry_count=0,
            rate_limit_status="not_called_disabled_default",
            order_endpoint_called=False,
            http_request_sent=False,
            signature_created=False,
            signed_request_created=False,
            blocked_before_http=True,
            real_exchange_response=False,
        ).to_dict()
        evidence["adapter_id"] = self.adapter_id
        evidence["venue"] = self.venue
        evidence["environment"] = self.environment
        evidence["actual_network_calls_enabled"] = False
        return evidence

    def place_order(self, *, intent: OneOrderRuntimeIntent, idempotency_key: str, secret_reference_id: str) -> Mapping[str, Any]:
        return self.prepare_disabled_submit_evidence(intent=intent, idempotency_key=idempotency_key)


def validate_runtime_arming_evidence(
    evidence: Mapping[str, Any] | SingleSignedTestnetRuntimeArmingEvidence | None,
    *,
    expected_p5_sha256: str | None = None,
) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, SingleSignedTestnetRuntimeArmingEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not _is_nonempty(payload.get("operator_id")):
        blockers.append("P6_OPERATOR_ID_MISSING")
    if not _is_nonempty(payload.get("approval_ticket_id")):
        blockers.append("P6_APPROVAL_TICKET_ID_MISSING")
    if payload.get("explicit_runtime_arming_text") != P6_EXPLICIT_RUNTIME_ARMING_PHRASE:
        blockers.append("P6_EXPLICIT_RUNTIME_ARMING_PHRASE_MISSING_OR_MISMATCHED")
    if payload.get("local_console_confirmed") is not True:
        blockers.append("P6_LOCAL_CONSOLE_CONFIRMATION_REQUIRED")
    if payload.get("human_operator_submitted") is not True:
        blockers.append("P6_HUMAN_OPERATOR_SUBMISSION_REQUIRED")
    if payload.get("testnet_only") is not True:
        blockers.append("P6_TESTNET_ONLY_NOT_TRUE")
    if payload.get("btcusdt_only") is not True:
        blockers.append("P6_BTCUSDT_ONLY_NOT_TRUE")
    if payload.get("max_order_count") != 1:
        blockers.append("P6_MAX_ORDER_COUNT_NOT_ONE")
    if payload.get("low_notional_cap_confirmed") is not True:
        blockers.append("P6_LOW_NOTIONAL_CAP_NOT_CONFIRMED")
    if payload.get("no_auto_generated_runtime_approval_file") is not True:
        blockers.append("P6_AUTO_GENERATED_RUNTIME_APPROVAL_FILE_NOT_ALLOWED")
    if payload.get("understands_real_order_endpoint_may_be_called_when_armed") is not True:
        blockers.append("P6_OPERATOR_ENDPOINT_CALL_ACKNOWLEDGEMENT_REQUIRED")
    if expected_p5_sha256 and not payload.get("source_p5_action_time_boundary_sha256"):
        blockers.append("P6_SOURCE_P5_ACTION_TIME_BOUNDARY_HASH_MISSING")
    if expected_p5_sha256 and payload.get("source_p5_action_time_boundary_sha256") and payload.get("source_p5_action_time_boundary_sha256") != expected_p5_sha256:
        blockers.append("P6_SOURCE_P5_ACTION_TIME_BOUNDARY_HASH_MISMATCH")

    validation = {
        "runtime_arming_evidence_valid": not blockers,
        "runtime_arming_block_reasons": sorted(dict.fromkeys(blockers)),
        "operator_id": payload.get("operator_id"),
        "approval_ticket_id": payload.get("approval_ticket_id"),
        "explicit_runtime_arming_phrase_matched": payload.get("explicit_runtime_arming_text") == P6_EXPLICIT_RUNTIME_ARMING_PHRASE,
        "runtime_network_call_allowed_by_operator": payload.get("runtime_network_call_allowed_by_operator") is True,
        "execute_real_submit_now": payload.get("execute_real_submit_now") is True,
        "source_p5_action_time_boundary_sha256": payload.get("source_p5_action_time_boundary_sha256"),
        "expected_p5_action_time_boundary_sha256": expected_p5_sha256,
    }
    validation["runtime_arming_validation_sha256"] = sha256_json(validation)
    return validation


def validate_runtime_freshness_evidence(
    evidence: Mapping[str, Any] | SingleSignedTestnetRuntimeFreshnessEvidence | None,
    *,
    max_action_time_boundary_age_sec: int = 60,
    max_endpoint_time_sync_age_ms: int = 1000,
    max_hot_path_risk_gate_age_sec: int = 30,
) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, SingleSignedTestnetRuntimeFreshnessEvidence) else dict(evidence or {})
    blockers: list[str] = []
    action_age = int(payload.get("action_time_boundary_age_sec", 10**9) or 10**9)
    endpoint_age = int(payload.get("endpoint_time_sync_age_ms", 10**9) or 10**9)
    risk_age = int(payload.get("hot_path_preorder_risk_gate_age_sec", 10**9) or 10**9)
    if action_age > max_action_time_boundary_age_sec:
        blockers.append("P6_ACTION_TIME_BOUNDARY_STALE_AT_RUNTIME")
    if endpoint_age > max_endpoint_time_sync_age_ms:
        blockers.append("P6_ENDPOINT_TIME_SYNC_STALE_AT_RUNTIME")
    if risk_age > max_hot_path_risk_gate_age_sec:
        blockers.append("P6_HOT_PATH_PREORDER_RISK_GATE_STALE_AT_RUNTIME")
    if payload.get("hot_path_preorder_risk_gate_result") not in _ALLOWED_RISK_GATE_RESULTS:
        blockers.append("P6_HOT_PATH_PREORDER_RISK_GATE_NOT_PASSED_FOR_SIGNED_TESTNET")
    if payload.get("duplicate_submit_lock_acquired") is not True:
        blockers.append("P6_DUPLICATE_SUBMIT_LOCK_NOT_ACQUIRED")
    if payload.get("idempotency_key_already_seen") is True:
        blockers.append("P6_IDEMPOTENCY_KEY_ALREADY_SEEN")
    if payload.get("post_submit_relock_ready") is not True:
        blockers.append("P6_POST_SUBMIT_RELOCK_NOT_READY")
    if payload.get("manual_kill_switch_confirmed_safe") is not True:
        blockers.append("P6_MANUAL_KILL_SWITCH_NOT_SAFE")
    if payload.get("config_kill_switch_enabled") is True:
        blockers.append("P6_CONFIG_KILL_SWITCH_ENABLED")
    if payload.get("daily_loss_cap_within_limit") is not True:
        blockers.append("P6_DAILY_LOSS_CAP_BREACHED")
    if payload.get("consecutive_loss_cap_within_limit") is not True:
        blockers.append("P6_CONSECUTIVE_LOSS_CAP_BREACHED")
    if payload.get("api_error_rate_within_limit") is not True:
        blockers.append("P6_API_ERROR_RATE_LIMIT_BREACHED")
    if payload.get("reconciliation_mismatch_within_limit") is not True:
        blockers.append("P6_RECONCILIATION_MISMATCH_LIMIT_BREACHED")
    if payload.get("stale_data_kill_switch_active") is True:
        blockers.append("P6_STALE_DATA_KILL_SWITCH_ACTIVE")
    if payload.get("hard_required_price_source_missing") is True:
        blockers.append("P6_HARD_REQUIRED_PRICE_SOURCE_MISSING")
    if payload.get("venue_testnet_ready") is not True:
        blockers.append("P6_TESTNET_VENUE_NOT_READY")
    if payload.get("adapter_symbol_filter_passed") is not True:
        blockers.append("P6_ADAPTER_SYMBOL_FILTER_NOT_PASSED")
    if payload.get("monitoring_evidence_sink_ready") is not True:
        blockers.append("P6_MONITORING_EVIDENCE_SINK_NOT_READY")

    validation = {
        "runtime_freshness_evidence_valid": not blockers,
        "runtime_freshness_block_reasons": sorted(dict.fromkeys(blockers)),
        "action_time_boundary_age_sec": action_age,
        "max_action_time_boundary_age_sec": max_action_time_boundary_age_sec,
        "endpoint_time_sync_age_ms": endpoint_age,
        "max_endpoint_time_sync_age_ms": max_endpoint_time_sync_age_ms,
        "hot_path_preorder_risk_gate_age_sec": risk_age,
        "max_hot_path_risk_gate_age_sec": max_hot_path_risk_gate_age_sec,
        "hot_path_preorder_risk_gate_result": payload.get("hot_path_preorder_risk_gate_result"),
        "duplicate_submit_lock_acquired": payload.get("duplicate_submit_lock_acquired") is True,
        "idempotency_key_already_seen": payload.get("idempotency_key_already_seen") is True,
        "post_submit_relock_ready": payload.get("post_submit_relock_ready") is True,
    }
    validation["runtime_freshness_validation_sha256"] = sha256_json(validation)
    return validation


def _p5_ready(p5_report: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    data = dict(p5_report or {})
    if data.get("status") != "P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_VALID_REVIEW_ONLY_NO_SUBMIT":
        blockers.append("P6_P5_ACTION_TIME_BOUNDARY_STATUS_NOT_VALID")
    if data.get("action_time_submit_preconditions_valid_review_only") is not True:
        blockers.append("P6_P5_ACTION_TIME_PRECONDITIONS_NOT_VALID")
    if data.get("actual_order_submission_performed") is not False:
        blockers.append("P6_P5_ACTUAL_ORDER_SUBMISSION_PERFORMED_NOT_FALSE")
    if data.get("order_endpoint_called") is not False:
        blockers.append("P6_P5_ORDER_ENDPOINT_CALLED_NOT_FALSE")
    if data.get("secret_value_accessed") is not False:
        blockers.append("P6_P5_SECRET_VALUE_ACCESSED_NOT_FALSE")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append("P6_P5_TESTNET_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    return not blockers, blockers


def _redacted_request_preview(intent: OneOrderRuntimeIntent, idempotency_key: str) -> dict[str, Any]:
    return {
        "symbol": intent.symbol,
        "side": intent.side,
        "type": intent.order_type,
        "quantity": intent.quantity,
        "newClientOrderId": idempotency_key,
        "stage": "signed_testnet_runtime_submit",
        "secret_reference_only": True,
    }


def _normalize_adapter_response(response: Mapping[str, Any], *, intent: OneOrderRuntimeIntent, idempotency_key: str) -> dict[str, Any]:
    payload = dict(response or {})
    exchange_order_id = payload.get("exchange_order_id") or payload.get("orderId") or payload.get("clientOrderId")
    status = str(payload.get("exchange_order_status") or payload.get("status") or "").upper()
    evidence = {
        "endpoint_type": payload.get("endpoint_type", "signed_testnet_private_place_order"),
        "method": payload.get("method", "POST"),
        "request_hash": payload.get("request_hash") or sha256_json(_redacted_request_preview(intent, idempotency_key)),
        "response_hash": payload.get("response_hash") or sha256_json({k: v for k, v in payload.items() if "secret" not in str(k).lower() and "key" not in str(k).lower()}),
        "timestamp_utc": payload.get("timestamp_utc") or utc_now_canonical(),
        "idempotency_key": idempotency_key,
        "retry_count": int(payload.get("retry_count", 0) or 0),
        "rate_limit_status": payload.get("rate_limit_status", "unknown"),
        "order_endpoint_called": payload.get("order_endpoint_called") is True,
        "http_request_sent": payload.get("http_request_sent") is True,
        "signature_created": payload.get("signature_created") is True,
        "signed_request_created": payload.get("signed_request_created") is True,
        "secret_value_logged": payload.get("secret_value_logged") is True,
        "api_key_value_logged": payload.get("api_key_value_logged") is True,
        "api_secret_value_logged": payload.get("api_secret_value_logged") is True,
        "blocked_before_http": payload.get("blocked_before_http") is True,
        "exchange_order_id": str(exchange_order_id) if exchange_order_id else None,
        "exchange_order_status": status or None,
        "real_exchange_response": payload.get("real_exchange_response") is True,
    }
    evidence["endpoint_submit_evidence_sha256"] = sha256_json(evidence)
    return evidence


def validate_exchange_submit_evidence(evidence: Mapping[str, Any] | None, *, require_real_exchange_response: bool) -> dict[str, Any]:
    payload = dict(evidence or {})
    blockers: list[str] = []
    if require_real_exchange_response:
        if payload.get("order_endpoint_called") is not True:
            blockers.append("P6_ORDER_ENDPOINT_NOT_CALLED")
        if payload.get("http_request_sent") is not True:
            blockers.append("P6_HTTP_REQUEST_NOT_SENT")
        if payload.get("signature_created") is not True:
            blockers.append("P6_SIGNATURE_NOT_CREATED")
        if payload.get("signed_request_created") is not True:
            blockers.append("P6_SIGNED_REQUEST_NOT_CREATED")
        if not _is_nonempty(payload.get("exchange_order_id")):
            blockers.append("P6_EXCHANGE_ORDER_ID_MISSING")
        if payload.get("exchange_order_status") not in _ALLOWED_ORDER_STATUSES:
            blockers.append("P6_EXCHANGE_ORDER_STATUS_INVALID_OR_MISSING")
        if payload.get("real_exchange_response") is not True:
            blockers.append("P6_REAL_EXCHANGE_RESPONSE_NOT_CONFIRMED")
    if payload.get("secret_value_logged") is True:
        blockers.append("P6_SECRET_VALUE_LOGGED")
    if payload.get("api_key_value_logged") is True:
        blockers.append("P6_API_KEY_VALUE_LOGGED")
    if payload.get("api_secret_value_logged") is True:
        blockers.append("P6_API_SECRET_VALUE_LOGGED")
    if payload.get("retry_count", 0) not in range(0, 4):
        blockers.append("P6_RETRY_COUNT_OUT_OF_POLICY")

    validation = {
        "exchange_submit_evidence_valid": not blockers,
        "exchange_submit_block_reasons": sorted(dict.fromkeys(blockers)),
        "require_real_exchange_response": require_real_exchange_response,
        "order_endpoint_called": payload.get("order_endpoint_called") is True,
        "http_request_sent": payload.get("http_request_sent") is True,
        "signature_created": payload.get("signature_created") is True,
        "signed_request_created": payload.get("signed_request_created") is True,
        "exchange_order_id_present": _is_nonempty(payload.get("exchange_order_id")),
        "exchange_order_status": payload.get("exchange_order_status"),
        "real_exchange_response": payload.get("real_exchange_response") is True,
        "secret_value_logged": payload.get("secret_value_logged") is True,
    }
    validation["exchange_submit_validation_sha256"] = sha256_json(validation)
    return validation


def build_single_signed_testnet_submit_runtime_action_report(
    *,
    cfg: AppConfig | None = None,
    intent: OneOrderRuntimeIntent | None = None,
    arming_evidence: SingleSignedTestnetRuntimeArmingEvidence | Mapping[str, Any] | None = None,
    freshness_evidence: SingleSignedTestnetRuntimeFreshnessEvidence | Mapping[str, Any] | None = None,
    secret_binding: RuntimeSecretBindingMetadata | Mapping[str, Any] | None = None,
    existing_idempotency_keys: Sequence[str] | None = None,
    adapter: SignedTestnetSubmitAdapter | DisabledByDefaultSignedTestnetSubmitAdapter | None = None,
    execute_submit: bool = False,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    p5_report = _read_latest_json(cfg, "p5_action_time_submit_approval_boundary_report.json")
    p5_ok, p5_blockers = _p5_ready(p5_report)
    p5_hash = _public_hash(p5_report)

    intent = intent or OneOrderRuntimeIntent(idempotency_key="p6_single_signed_testnet_submit_idempotency_key")
    idempotency_key = intent.resolved_idempotency_key()
    arming_evidence = arming_evidence or SingleSignedTestnetRuntimeArmingEvidence(source_p5_action_time_boundary_sha256=p5_hash)
    freshness_evidence = freshness_evidence or SingleSignedTestnetRuntimeFreshnessEvidence()
    secret_binding = secret_binding or RuntimeSecretBindingMetadata(secret_reference_id="metadata_only_testnet_key_ref_runtime_submit", key_fingerprint_sha256="4" * 64)
    adapter = adapter or DisabledByDefaultSignedTestnetSubmitAdapter()

    arming_payload = arming_evidence.to_dict() if isinstance(arming_evidence, SingleSignedTestnetRuntimeArmingEvidence) else dict(arming_evidence or {})
    freshness_payload = freshness_evidence.to_dict() if isinstance(freshness_evidence, SingleSignedTestnetRuntimeFreshnessEvidence) else dict(freshness_evidence or {})
    secret_payload = secret_binding.to_dict() if isinstance(secret_binding, RuntimeSecretBindingMetadata) else dict(secret_binding or {})

    arming_validation = validate_runtime_arming_evidence(arming_payload, expected_p5_sha256=p5_hash)
    freshness_validation = validate_runtime_freshness_evidence(freshness_payload)
    secret_validation = validate_runtime_secret_binding_metadata(secret_payload)
    one_order_guard = validate_one_order_guard(intent, idempotency_key=idempotency_key, existing_idempotency_keys=existing_idempotency_keys)

    submit_requested = bool(execute_submit or arming_payload.get("execute_real_submit_now") is True)
    runtime_network_allowed = arming_payload.get("runtime_network_call_allowed_by_operator") is True
    adapter_is_real = getattr(adapter, "real_endpoint_adapter", False) is True
    adapter_boundary_evidence = _adapter_boundary_from_adapter(adapter, submit_requested=submit_requested)
    adapter_boundary_validation = validate_signed_testnet_adapter_boundary(adapter_boundary_evidence, submit_requested=submit_requested)
    preconditions_ok = bool(
        p5_ok
        and arming_validation["runtime_arming_evidence_valid"]
        and freshness_validation["runtime_freshness_evidence_valid"]
        and secret_validation["secret_binding_metadata_valid"]
        and one_order_guard["one_order_guard_passed"]
        and adapter_boundary_validation["adapter_boundary_valid"]
    )

    blockers = sorted(dict.fromkeys(
        p5_blockers
        + list(arming_validation["runtime_arming_block_reasons"])
        + list(freshness_validation["runtime_freshness_block_reasons"])
        + list(secret_validation["secret_binding_block_reasons"])
        + list(one_order_guard["one_order_guard_block_reasons"])
        + list(adapter_boundary_validation["adapter_boundary_block_reasons"])
    ))

    if submit_requested and not runtime_network_allowed:
        blockers.append("P6_RUNTIME_NETWORK_CALL_NOT_ALLOWED_BY_OPERATOR")
    if submit_requested and not adapter_is_real:
        blockers.append("P6_REAL_SIGNED_TESTNET_ENDPOINT_ADAPTER_NOT_ATTACHED")
    if submit_requested and not preconditions_ok:
        blockers.append("P6_SUBMIT_REQUESTED_WITH_INVALID_PRECONDITIONS")

    performed_submit = False
    endpoint_evidence: dict[str, Any]
    if submit_requested and preconditions_ok and runtime_network_allowed and adapter_is_real:
        raw_response = adapter.place_order(intent=intent, idempotency_key=str(idempotency_key), secret_reference_id=str(secret_payload.get("secret_reference_id")))
        endpoint_evidence = _normalize_adapter_response(raw_response, intent=intent, idempotency_key=str(idempotency_key))
        exchange_validation = validate_exchange_submit_evidence(endpoint_evidence, require_real_exchange_response=True)
        performed_submit = exchange_validation["exchange_submit_evidence_valid"]
        blockers.extend(exchange_validation["exchange_submit_block_reasons"])
    else:
        disabled_adapter = DisabledByDefaultSignedTestnetSubmitAdapter()
        endpoint_evidence = disabled_adapter.prepare_disabled_submit_evidence(intent=intent, idempotency_key=str(idempotency_key))
        exchange_validation = validate_exchange_submit_evidence(endpoint_evidence, require_real_exchange_response=False)
        blockers.extend(exchange_validation["exchange_submit_block_reasons"])

    blockers = sorted(dict.fromkeys(blockers))
    ready_disabled = bool(preconditions_ok and not submit_requested and not blockers)
    submitted_ok = bool(performed_submit and not blockers)
    status = STATUS_SUBMITTED_BY_EXTERNAL_RUNTIME if submitted_ok else (STATUS_READY_DISABLED_NO_SUBMIT if ready_disabled else STATUS_BLOCKED_FAIL_CLOSED)
    external_runtime_preflight_report = build_p6_external_runtime_preflight_report(
        p5_ok=p5_ok,
        arming_validation=arming_validation,
        freshness_validation=freshness_validation,
        secret_validation=secret_validation,
        one_order_guard=one_order_guard,
        adapter_boundary_validation=adapter_boundary_validation,
        submit_requested=submit_requested,
        runtime_network_allowed=runtime_network_allowed,
    )

    report = {
        "artifact_type": "p6_single_signed_testnet_submit_runtime_action",
        "p6_single_signed_testnet_submit_runtime_action_version": P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only_default": not submitted_ok,
        "runtime_action_boundary_separate_from_review_package": True,
        "local_operator_runtime_only": True,
        "p5_action_time_boundary_valid": p5_ok,
        "source_p5_action_time_boundary_hash": p5_hash,
        "source_p5_action_time_boundary_id": p5_report.get("p5_action_time_submit_approval_boundary_id"),
        "runtime_arming_validation": arming_validation,
        "runtime_arming_evidence": arming_payload,
        "runtime_freshness_validation": freshness_validation,
        "runtime_freshness_evidence": freshness_payload,
        "secret_binding_validation": secret_validation,
        "secret_binding_metadata_evidence": secret_payload,
        "one_order_guard": one_order_guard,
        "adapter_boundary_evidence": adapter_boundary_evidence,
        "adapter_boundary_validation": adapter_boundary_validation,
        "external_runtime_preflight_report": external_runtime_preflight_report,
        "idempotency_key": idempotency_key,
        "submit_requested": submit_requested,
        "runtime_network_call_allowed_by_operator": runtime_network_allowed,
        "real_endpoint_adapter_attached": adapter_is_real,
        "adapter_id": getattr(adapter, "adapter_id", "unknown_adapter"),
        "venue": getattr(adapter, "venue", "unknown"),
        "environment": getattr(adapter, "environment", "unknown"),
        "endpoint_submit_evidence": endpoint_evidence,
        "exchange_submit_validation": exchange_validation,
        "post_submit_relock_evidence": {
            "post_submit_relock_required": True,
            "post_submit_relock_applied": bool(submitted_ok),
            "place_order_enabled_after_action": False,
            "cancel_order_enabled_after_action": False,
            "signed_order_executor_enabled_after_action": False,
            "testnet_order_submission_allowed_after_action": False,
            "order_endpoint_call_allowed_after_action": False,
            "signature_creation_allowed_after_action": False,
            "http_request_allowed_after_action": False,
        },
        "post_submit_next_required_evidence": {
            "post_submit_order_id_intake_required": bool(submitted_ok),
            "status_polling_required": bool(submitted_ok),
            "cancel_boundary_required_if_unfilled_or_timeout": bool(submitted_ok),
            "signed_testnet_reconciliation_required": bool(submitted_ok),
            "signed_testnet_session_close_required": bool(submitted_ok),
        },
        "block_reasons": blockers,
        "created_at_utc": created_at_utc,
        **_disabled_payload(
            endpoint_called=bool(endpoint_evidence.get("order_endpoint_called") is True and submitted_ok),
            http_request_sent=bool(endpoint_evidence.get("http_request_sent") is True and submitted_ok),
            submitted=submitted_ok,
        ),
    }
    report["unsafe_truthy_execution_flags"] = [] if submitted_ok else truthy_execution_flags(report)
    if not submitted_ok and report["unsafe_truthy_execution_flags"]:
        report["blocked"] = True
        report["fail_closed"] = True
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P6_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p6_single_signed_testnet_submit_runtime_action_id"] = stable_id("p6_single_signed_testnet_submit_runtime_action", report, 24)
    report["p6_single_signed_testnet_submit_runtime_action_sha256"] = sha256_json(report)
    return report


def build_p6_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p5 = _read_latest_json(cfg, "p5_action_time_submit_approval_boundary_report.json")
    p5_hash = _public_hash(p5)
    base_arm = SingleSignedTestnetRuntimeArmingEvidence(source_p5_action_time_boundary_sha256=p5_hash)
    base_secret = RuntimeSecretBindingMetadata(secret_reference_id="metadata_only_testnet_key_ref_runtime_submit", key_fingerprint_sha256="5" * 64)
    duplicate_key = "p6_duplicate_idempotency_fixture"
    cases: dict[str, dict[str, Any]] = {
        "missing_runtime_arming_phrase": {
            "arm": {**base_arm.to_dict(), "explicit_runtime_arming_text": "approve"},
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p6_missing_phrase_fixture"),
            "existing": [],
            "execute": False,
        },
        "submit_requested_without_operator_network_allowance": {
            "arm": {**base_arm.to_dict(), "execute_real_submit_now": True, "runtime_network_call_allowed_by_operator": False},
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p6_no_network_allowance_fixture"),
            "existing": [],
            "execute": True,
        },
        "submit_requested_without_real_adapter": {
            "arm": {**base_arm.to_dict(), "execute_real_submit_now": True, "runtime_network_call_allowed_by_operator": True},
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p6_no_real_adapter_fixture"),
            "existing": [],
            "execute": True,
        },
        "stale_runtime_risk_gate": {
            "arm": base_arm,
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(hot_path_preorder_risk_gate_age_sec=120),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p6_stale_risk_fixture"),
            "existing": [],
            "execute": False,
        },
        "duplicate_idempotency": {
            "arm": base_arm,
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(idempotency_key_already_seen=True),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key=duplicate_key),
            "existing": [duplicate_key],
            "execute": False,
        },
        "kill_switch_enabled": {
            "arm": base_arm,
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(config_kill_switch_enabled=True),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p6_kill_switch_fixture"),
            "existing": [],
            "execute": False,
        },
        "hard_cap_exceeded": {
            "arm": base_arm,
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p6_hard_cap_fixture", quantity=1.0, reference_price=50000.0, max_notional=10.0),
            "existing": [],
            "execute": False,
        },
        "invalid_secret_scope": {
            "arm": base_arm,
            "fresh": SingleSignedTestnetRuntimeFreshnessEvidence(),
            "secret": {**base_secret.to_dict(), "key_scope": "live_trade"},
            "intent": OneOrderRuntimeIntent(idempotency_key="p6_invalid_secret_scope_fixture"),
            "existing": [],
            "execute": False,
        },
    }
    results: dict[str, Any] = {}
    for name, fixture in cases.items():
        report = build_single_signed_testnet_submit_runtime_action_report(
            cfg=cfg,
            arming_evidence=fixture["arm"],
            freshness_evidence=fixture["fresh"],
            secret_binding=fixture["secret"],
            intent=fixture["intent"],
            existing_idempotency_keys=fixture["existing"],
            execute_submit=fixture["execute"],
        )
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "actual_order_submission_performed": report["actual_order_submission_performed"],
            "order_endpoint_called": report["order_endpoint_called"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    payload = {
        "artifact_type": "p6_single_signed_testnet_submit_runtime_action_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        **_disabled_payload(),
    }
    payload["p6_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_single_signed_testnet_submit_runtime_action(
    *,
    cfg: AppConfig | None = None,
    intent: OneOrderRuntimeIntent | None = None,
    arming_evidence: SingleSignedTestnetRuntimeArmingEvidence | Mapping[str, Any] | None = None,
    freshness_evidence: SingleSignedTestnetRuntimeFreshnessEvidence | Mapping[str, Any] | None = None,
    secret_binding: RuntimeSecretBindingMetadata | Mapping[str, Any] | None = None,
    existing_idempotency_keys: Sequence[str] | None = None,
    adapter: SignedTestnetSubmitAdapter | DisabledByDefaultSignedTestnetSubmitAdapter | None = None,
    execute_submit: bool = False,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_single_signed_testnet_submit_runtime_action_report(
        cfg=cfg,
        intent=intent,
        arming_evidence=arming_evidence,
        freshness_evidence=freshness_evidence,
        secret_binding=secret_binding,
        existing_idempotency_keys=existing_idempotency_keys,
        adapter=adapter,
        execute_submit=execute_submit,
    )
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p6_single_signed_testnet_submit_runtime_action")
    negative = build_p6_negative_fixture_results(cfg=cfg)
    registry_record = append_registry_record(
        registry_path(cfg, P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_REGISTRY_NAME),
        {
            "artifact_type": "p6_single_signed_testnet_submit_runtime_action_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p6_single_signed_testnet_submit_runtime_action_id": report["p6_single_signed_testnet_submit_runtime_action_id"],
            "p6_single_signed_testnet_submit_runtime_action_sha256": report["p6_single_signed_testnet_submit_runtime_action_sha256"],
            "source_p5_action_time_boundary_hash": report.get("source_p5_action_time_boundary_hash"),
            "submit_requested": report["submit_requested"],
            "actual_order_submission_performed": report["actual_order_submission_performed"],
            "actual_testnet_order_submitted": report["actual_testnet_order_submitted"],
            "order_endpoint_called": report["order_endpoint_called"],
            "http_request_sent": report["http_request_sent"],
            "real_exchange_order_id_present": report["real_exchange_order_id_present"],
            "secret_value_accessed": report["secret_value_accessed"],
            "testnet_order_submission_allowed": report["testnet_order_submission_allowed"],
            "live_canary_execution_enabled": report["live_canary_execution_enabled"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
        },
        registry_name=P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_REGISTRY_NAME,
        id_field="p6_single_signed_testnet_submit_runtime_action_registry_record_id",
        hash_field="p6_single_signed_testnet_submit_runtime_action_registry_record_sha256",
        id_prefix="p6_single_signed_testnet_submit_runtime_action_registry_record",
    )
    report["p6_single_signed_testnet_submit_runtime_action_registry_record_id"] = registry_record["p6_single_signed_testnet_submit_runtime_action_registry_record_id"]
    report["p6_single_signed_testnet_submit_runtime_action_registry_record_sha256"] = registry_record["p6_single_signed_testnet_submit_runtime_action_registry_record_sha256"]
    report["p6_single_signed_testnet_submit_runtime_action_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p6_single_signed_testnet_submit_runtime_action_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only_default": report["review_only_default"],
        "p5_action_time_boundary_valid": report["p5_action_time_boundary_valid"],
        "submit_requested": report["submit_requested"],
        "runtime_network_call_allowed_by_operator": report["runtime_network_call_allowed_by_operator"],
        "real_endpoint_adapter_attached": report["real_endpoint_adapter_attached"],
        "adapter_boundary_valid": report["adapter_boundary_validation"]["adapter_boundary_valid"],
        "external_runtime_preflight_passed": report["external_runtime_preflight_report"]["preflight_passed"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "actual_testnet_order_submitted": report["actual_testnet_order_submitted"],
        "order_endpoint_called": report["order_endpoint_called"],
        "http_request_sent": report["http_request_sent"],
        "signature_created": report["signature_created"],
        "signed_request_created": report["signed_request_created"],
        "real_exchange_order_id_present": report["real_exchange_order_id_present"],
        "secret_value_accessed": report["secret_value_accessed"],
        "secret_value_logged": report["secret_value_logged"],
        "testnet_order_submission_allowed": report["testnet_order_submission_allowed"],
        "post_submit_relock_required": report["post_submit_relock_evidence"]["post_submit_relock_required"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p6_single_signed_testnet_submit_runtime_action_id": report["p6_single_signed_testnet_submit_runtime_action_id"],
        "p6_single_signed_testnet_submit_runtime_action_sha256": report["p6_single_signed_testnet_submit_runtime_action_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p6_summary_sha256"] = sha256_json(summary)
    for path in [
        latest / "p6_single_signed_testnet_submit_runtime_action_report.json",
        storage / "p6_single_signed_testnet_submit_runtime_action_report.json",
    ]:
        atomic_write_json(path, report)
    atomic_write_json(latest / "p6_single_signed_testnet_submit_runtime_action_negative_fixture_results.json", negative)
    atomic_write_json(storage / "p6_single_signed_testnet_submit_runtime_action_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p6_external_runtime_preflight_report.json", report["external_runtime_preflight_report"])
    atomic_write_json(storage / "p6_external_runtime_preflight_report.json", report["external_runtime_preflight_report"])
    atomic_write_json(latest / "p6_single_signed_testnet_submit_runtime_action_registry_record.json", registry_record)
    atomic_write_json(storage / "p6_single_signed_testnet_submit_runtime_action_registry_record.json", registry_record)
    atomic_write_json(latest / "p6_single_signed_testnet_submit_runtime_action_summary.json", summary)
    atomic_write_json(storage / "p6_single_signed_testnet_submit_runtime_action_summary.json", summary)
    return report


__all__ = [
    "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_VERSION",
    "STATUS_READY_DISABLED_NO_SUBMIT",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "STATUS_SUBMITTED_BY_EXTERNAL_RUNTIME",
    "P6_EXPLICIT_RUNTIME_ARMING_PHRASE",
    "SingleSignedTestnetRuntimeArmingEvidence",
    "SingleSignedTestnetRuntimeFreshnessEvidence",
    "DisabledByDefaultSignedTestnetSubmitAdapter",
    "validate_runtime_arming_evidence",
    "validate_runtime_freshness_evidence",
    "validate_exchange_submit_evidence",
    "build_single_signed_testnet_submit_runtime_action_report",
    "build_p6_negative_fixture_results",
    "persist_single_signed_testnet_submit_runtime_action",
]
