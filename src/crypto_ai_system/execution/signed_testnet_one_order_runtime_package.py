from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.idempotency import make_idempotency_key
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P4_SIGNED_TESTNET_RUNTIME_PACKAGE_VERSION = "p4_signed_testnet_one_order_runtime_package_v1"
P4_SIGNED_TESTNET_RUNTIME_PACKAGE_REGISTRY_NAME = "p4_signed_testnet_one_order_runtime_package_registry"

STATUS_READY_REVIEW_ONLY = "P4_SIGNED_TESTNET_ONE_ORDER_RUNTIME_PACKAGE_READY_REVIEW_ONLY_DISABLED"
STATUS_BLOCKED_REVIEW_ONLY = "P4_SIGNED_TESTNET_ONE_ORDER_RUNTIME_PACKAGE_BLOCKED_REVIEW_ONLY"

_ALLOWED_SIDES = {"BUY", "SELL"}
_ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT"}
_ALLOWED_SYMBOLS = {"BTCUSDT"}
_ALLOWED_KEY_SCOPES = {"testnet_trade_only", "signed_testnet_trade_only", "testnet_order_submit_only"}
_DISABLED_ENDPOINT_FLAGS = {
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
    "secret_file_accessed": False,
    "secret_file_created": False,
    "runtime_settings_mutated": False,
    "score_weights_mutated": False,
    "candidate_profile_applied": False,
    "auto_promotion_allowed": False,
    "ready_for_signed_testnet_execution": False,
    "testnet_order_submission_allowed": False,
    "signed_testnet_promotion_allowed": False,
    "external_order_submission_allowed": False,
    "place_order_enabled": False,
    "cancel_order_enabled": False,
    "signed_order_executor_enabled": False,
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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _public_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase_d_candidate_manual_approval_chain_report_sha256",
        "approval_registry_record_sha256",
        "phase_d_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


@dataclass(frozen=True)
class RuntimeSecretBindingMetadata:
    """Metadata-only testnet key binding evidence.

    The object intentionally carries no API key, secret, passphrase, private key,
    or file path. Runtime processes that later perform a real testnet submit must
    bind secrets outside this review-only package and persist only this metadata.
    """

    secret_reference_id: str
    key_fingerprint_sha256: str
    venue: str = "binance_futures_testnet"
    environment: str = "testnet"
    key_scope: str = "testnet_trade_only"
    metadata_only: bool = True
    secret_value_accessed: bool = False
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False
    private_key_logged: bool = False
    passphrase_logged: bool = False
    secret_file_accessed: bool = False
    secret_file_created: bool = False
    withdrawal_permission_enabled: bool = False
    transfer_permission_enabled: bool = False
    admin_permission_enabled: bool = False
    live_or_mainnet_key_scope: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["secret_value_present_in_payload"] = False
        payload["secret_value_accessed"] = False
        payload["secret_value_logged"] = False
        payload["secret_file_accessed"] = False
        payload["secret_file_created"] = False
        payload["metadata_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class OneOrderRuntimeIntent:
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: float = 0.001
    reference_price: float = 50000.0
    max_notional: float = 100.0
    daily_loss_cap: float = 100.0
    max_order_count: int = 1
    order_count_already_submitted: int = 0
    idempotency_key: str | None = None
    approval_packet_id: str | None = None
    approval_intake_id: str | None = None
    risk_gate_id: str | None = None
    order_intent_id: str | None = None
    hot_path_preorder_risk_gate_passed: bool = True
    hot_path_preorder_risk_gate_fresh: bool = True
    kill_switch_confirmed_safe: bool = True
    manual_kill_switch_engaged: bool = False
    allow_derived_idempotency_key: bool = True

    def notional(self) -> float:
        return float(self.quantity) * float(self.reference_price)

    def canonical_identity_seed(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "reference_price": self.reference_price,
            "approval_packet_id": self.approval_packet_id,
            "approval_intake_id": self.approval_intake_id,
            "risk_gate_id": self.risk_gate_id,
            "order_intent_id": self.order_intent_id,
            "stage": "signed_testnet_one_order",
        }

    def resolved_idempotency_key(self) -> str | None:
        if self.idempotency_key:
            return self.idempotency_key
        if not self.allow_derived_idempotency_key:
            return None
        return make_idempotency_key(self.canonical_identity_seed())

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["notional"] = self.notional()
        payload["idempotency_key"] = self.resolved_idempotency_key()
        payload["idempotency_key_derived_by_package"] = self.idempotency_key is None and self.allow_derived_idempotency_key is True
        return payload


class DisabledSignedTestnetEndpointAdapter:
    """Signed-testnet endpoint contract with all network paths disabled.

    It prepares auditable request/response hashes and endpoint boundary evidence,
    but it does not sign, send HTTP, or call exchange order/status/cancel endpoints.
    """

    adapter_id = "disabled_signed_testnet_endpoint_adapter_v1"
    venue = "binance_futures_testnet"
    environment = "testnet"
    real_endpoint_adapter = False
    place_order_endpoint_supported_by_contract = True
    order_status_endpoint_supported_by_contract = True
    cancel_endpoint_supported_by_contract = True
    server_time_sync_supported_by_contract = True
    recv_window_timestamp_supported_by_contract = True
    hmac_signing_supported_by_contract = True
    rate_limit_handling_supported_by_contract = True

    def _boundary_evidence(self, *, endpoint_type: str, method: str, request_payload: Mapping[str, Any], idempotency_key: str | None) -> dict[str, Any]:
        redacted_request = dict(request_payload)
        redacted_request.pop("api_key", None)
        redacted_request.pop("api_secret", None)
        redacted_request.pop("secret", None)
        evidence = {
            "adapter_id": self.adapter_id,
            "venue": self.venue,
            "environment": self.environment,
            "endpoint_type": endpoint_type,
            "method": method,
            "request_hash": sha256_json(redacted_request),
            "response_hash": None,
            "timestamp_utc": utc_now_canonical(),
            "idempotency_key": idempotency_key,
            "retry_count": 0,
            "rate_limit_status": "not_called_disabled_boundary",
            "server_time_sync_performed": False,
            "recv_window_timestamp_handled": False,
            "hmac_signing_supported_by_contract": self.hmac_signing_supported_by_contract,
            "signature_created": False,
            "signed_request_created": False,
            "http_request_sent": False,
            "endpoint_called": False,
            "order_endpoint_called": False,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "secret_value_logged": False,
            "api_key_value_logged": False,
            "api_secret_value_logged": False,
            "blocked_before_http": True,
            "disabled_by_design": True,
        }
        evidence["endpoint_boundary_evidence_sha256"] = sha256_json(evidence)
        return evidence

    def prepare_place_order_boundary(self, intent: OneOrderRuntimeIntent, *, idempotency_key: str | None) -> dict[str, Any]:
        request_payload = {
            "symbol": intent.symbol,
            "side": intent.side,
            "type": intent.order_type,
            "quantity": intent.quantity,
            "newClientOrderId": idempotency_key,
            "timestamp": "DISABLED_NOT_CREATED",
            "recvWindow": "DISABLED_NOT_CREATED",
        }
        return self._boundary_evidence(
            endpoint_type="signed_testnet_private_place_order",
            method="POST",
            request_payload=request_payload,
            idempotency_key=idempotency_key,
        )

    def prepare_status_boundary(self, *, symbol: str, idempotency_key: str | None) -> dict[str, Any]:
        return self._boundary_evidence(
            endpoint_type="signed_testnet_private_order_status",
            method="GET",
            request_payload={"symbol": symbol, "origClientOrderId": idempotency_key},
            idempotency_key=idempotency_key,
        )

    def prepare_cancel_boundary(self, *, symbol: str, idempotency_key: str | None) -> dict[str, Any]:
        return self._boundary_evidence(
            endpoint_type="signed_testnet_private_cancel_order",
            method="DELETE",
            request_payload={"symbol": symbol, "origClientOrderId": idempotency_key},
            idempotency_key=idempotency_key,
        )


def validate_runtime_secret_binding_metadata(metadata: Mapping[str, Any] | RuntimeSecretBindingMetadata | None) -> dict[str, Any]:
    payload = metadata.to_dict() if isinstance(metadata, RuntimeSecretBindingMetadata) else dict(metadata or {})
    blockers: list[str] = []
    if not payload.get("secret_reference_id"):
        blockers.append("P4_SECRET_REFERENCE_ID_MISSING")
    if not _is_sha256_hex(payload.get("key_fingerprint_sha256")):
        blockers.append("P4_KEY_FINGERPRINT_SHA256_INVALID")
    if payload.get("metadata_only") is not True:
        blockers.append("P4_SECRET_BINDING_NOT_METADATA_ONLY")
    if payload.get("environment") != "testnet":
        blockers.append("P4_SECRET_BINDING_ENVIRONMENT_NOT_TESTNET")
    if str(payload.get("key_scope") or "") not in _ALLOWED_KEY_SCOPES:
        blockers.append("P4_SECRET_BINDING_KEY_SCOPE_NOT_TESTNET_TRADE_ONLY")
    for field in (
        "secret_value_accessed",
        "secret_value_logged",
        "api_key_value_logged",
        "api_secret_value_logged",
        "private_key_logged",
        "passphrase_logged",
        "secret_file_accessed",
        "secret_file_created",
        "withdrawal_permission_enabled",
        "transfer_permission_enabled",
        "admin_permission_enabled",
        "live_or_mainnet_key_scope",
    ):
        if _safe_bool(payload.get(field)):
            blockers.append(f"P4_SECRET_BINDING_UNSAFE_TRUE:{field}")
    validation = {
        "secret_binding_metadata_valid": not blockers,
        "secret_binding_block_reasons": blockers,
        "secret_reference_id": payload.get("secret_reference_id"),
        "key_fingerprint_sha256": payload.get("key_fingerprint_sha256"),
        "metadata_only": payload.get("metadata_only") is True,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "secret_file_accessed": False,
        "secret_file_created": False,
    }
    validation["secret_binding_validation_sha256"] = sha256_json(validation)
    return validation


def _phase_d_ready(phase_d: Mapping[str, Any], approval_registry: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if phase_d.get("status") != "PHASE_D_CANDIDATE_MANUAL_APPROVAL_CHAIN_VALID_REVIEW_ONLY":
        blockers.append("P4_PHASE_D_MANUAL_APPROVAL_CHAIN_NOT_VALID")
    if phase_d.get("approval_registry_valid_review_outcome") is not True:
        blockers.append("P4_APPROVAL_REGISTRY_VALID_OUTCOME_MISSING_IN_PHASE_D")
    if phase_d.get("testnet_order_submission_allowed") is not False:
        blockers.append("P4_PHASE_D_TESTNET_ORDER_SUBMISSION_FLAG_NOT_FALSE")
    if phase_d.get("external_order_submission_performed") is not False:
        blockers.append("P4_PHASE_D_EXTERNAL_ORDER_SUBMISSION_PERFORMED_NOT_FALSE")
    if (approval_registry.get("status") or approval_registry.get("approval_registry_status")) != "APPROVAL_REGISTRY_VALID_REVIEW_ONLY":
        blockers.append("P4_APPROVAL_REGISTRY_STATUS_NOT_VALID_REVIEW_ONLY")
    if approval_registry.get("validation_status") != "valid_review_only_staging_approval":
        blockers.append("P4_APPROVAL_REGISTRY_VALIDATION_STATUS_NOT_REVIEW_ONLY_VALID")
    if approval_registry.get("testnet_order_submission_allowed") is not False and approval_registry.get("testnet_order_submission_allowed") is not None:
        blockers.append("P4_APPROVAL_REGISTRY_TESTNET_ORDER_SUBMISSION_FLAG_NOT_FALSE")
    return not blockers, blockers


def validate_one_order_guard(
    intent: OneOrderRuntimeIntent,
    *,
    idempotency_key: str | None,
    existing_idempotency_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    existing = set(existing_idempotency_keys or [])
    symbol = str(intent.symbol or "").upper()
    side = str(intent.side or "").upper()
    order_type = str(intent.order_type or "").upper()
    notional = intent.notional()

    if symbol not in _ALLOWED_SYMBOLS:
        blockers.append("P4_SYMBOL_SCOPE_BLOCKED")
    if side not in _ALLOWED_SIDES:
        blockers.append("P4_SIDE_SCOPE_BLOCKED")
    if order_type not in _ALLOWED_ORDER_TYPES:
        blockers.append("P4_ORDER_TYPE_SCOPE_BLOCKED")
    if idempotency_key is None:
        blockers.append("P4_IDEMPOTENCY_KEY_MISSING")
    if idempotency_key in existing:
        blockers.append("P4_DUPLICATE_IDEMPOTENCY_KEY_BLOCKED")
    if intent.max_order_count != 1:
        blockers.append("P4_MAX_ORDER_COUNT_MUST_EQUAL_ONE")
    if intent.order_count_already_submitted != 0:
        blockers.append("P4_ORDER_COUNT_ALREADY_SUBMITTED_BLOCKED")
    if intent.quantity <= 0:
        blockers.append("P4_QUANTITY_MUST_BE_POSITIVE")
    if intent.reference_price <= 0:
        blockers.append("P4_REFERENCE_PRICE_MUST_BE_POSITIVE")
    if intent.max_notional <= 0:
        blockers.append("P4_MAX_NOTIONAL_MUST_BE_POSITIVE")
    if notional > intent.max_notional:
        blockers.append("P4_LOW_NOTIONAL_CAP_EXCEEDED")
    if intent.daily_loss_cap <= 0:
        blockers.append("P4_DAILY_LOSS_CAP_MUST_BE_POSITIVE")
    if intent.hot_path_preorder_risk_gate_passed is not True:
        blockers.append("P4_HOT_PATH_PREORDER_RISK_GATE_NOT_PASSED")
    if intent.hot_path_preorder_risk_gate_fresh is not True:
        blockers.append("P4_HOT_PATH_PREORDER_RISK_GATE_NOT_FRESH")
    if intent.kill_switch_confirmed_safe is not True:
        blockers.append("P4_KILL_SWITCH_NOT_CONFIRMED_SAFE")
    if intent.manual_kill_switch_engaged is True:
        blockers.append("P4_MANUAL_KILL_SWITCH_ENGAGED")

    report = {
        "one_order_guard_passed": not blockers,
        "one_order_guard_block_reasons": blockers,
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "notional": notional,
        "max_notional": intent.max_notional,
        "daily_loss_cap": intent.daily_loss_cap,
        "max_order_count": intent.max_order_count,
        "order_count_already_submitted": intent.order_count_already_submitted,
        "idempotency_key": idempotency_key,
        "duplicate_submit_lock_checked": True,
        "duplicate_submit_lock_passed": bool(idempotency_key is not None and idempotency_key not in existing),
        "post_submit_relock_required": True,
    }
    report["one_order_guard_sha256"] = sha256_json(report)
    return report


def build_signed_testnet_one_order_runtime_package_report(
    *,
    cfg: AppConfig | None = None,
    intent: OneOrderRuntimeIntent | None = None,
    secret_binding: RuntimeSecretBindingMetadata | Mapping[str, Any] | None = None,
    existing_idempotency_keys: Sequence[str] | None = None,
    adapter: DisabledSignedTestnetEndpointAdapter | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    intent = intent or OneOrderRuntimeIntent()
    if secret_binding is None:
        secret_binding = RuntimeSecretBindingMetadata(
            secret_reference_id="metadata_only_testnet_key_ref",
            key_fingerprint_sha256="0" * 64,
        )
    adapter = adapter or DisabledSignedTestnetEndpointAdapter()
    created_at_utc = created_at_utc or utc_now_canonical()

    phase_d = _read_latest_json(cfg, "phase_d_candidate_manual_approval_chain_report.json")
    approval_registry = _read_latest_json(cfg, "approval_registry_record.json")
    phase_d_ok, phase_d_blockers = _phase_d_ready(phase_d, approval_registry)

    secret_payload = secret_binding.to_dict() if isinstance(secret_binding, RuntimeSecretBindingMetadata) else dict(secret_binding or {})
    secret_validation = validate_runtime_secret_binding_metadata(secret_payload)
    idempotency_key = intent.resolved_idempotency_key()
    one_order_guard = validate_one_order_guard(intent, idempotency_key=idempotency_key, existing_idempotency_keys=existing_idempotency_keys)

    place_boundary = adapter.prepare_place_order_boundary(intent, idempotency_key=idempotency_key)
    status_boundary = adapter.prepare_status_boundary(symbol=intent.symbol, idempotency_key=idempotency_key)
    cancel_boundary = adapter.prepare_cancel_boundary(symbol=intent.symbol, idempotency_key=idempotency_key)

    blockers = sorted(dict.fromkeys(
        phase_d_blockers
        + list(secret_validation["secret_binding_block_reasons"])
        + list(one_order_guard["one_order_guard_block_reasons"])
    ))
    ready = bool(phase_d_ok and secret_validation["secret_binding_metadata_valid"] and one_order_guard["one_order_guard_passed"])

    disabled_flags = default_execution_flag_state()
    disabled_flags.update(_DISABLED_ENDPOINT_FLAGS)

    source_summary = {
        "phase_d_candidate_manual_approval_chain_report": {
            "present": bool(phase_d),
            "status": phase_d.get("status"),
            "sha256": _public_hash(phase_d),
        },
        "approval_registry_record": {
            "present": bool(approval_registry),
            "status": approval_registry.get("status") or approval_registry.get("approval_registry_status"),
            "validation_status": approval_registry.get("validation_status"),
            "sha256": _public_hash(approval_registry),
        },
    }

    report = {
        "artifact_type": "p4_signed_testnet_one_order_runtime_package_review_only_disabled",
        "p4_signed_testnet_runtime_package_version": P4_SIGNED_TESTNET_RUNTIME_PACKAGE_VERSION,
        "status": STATUS_READY_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "still_disabled": True,
        "runtime_boundary_separate_from_review_package": True,
        "runtime_package_ready_for_separate_operator_submit_action_review_only": ready,
        "runtime_package_does_not_grant_submit_permission": True,
        "source_evidence_hash_summary": source_summary,
        "phase_d_manual_approval_chain_valid": phase_d_ok,
        "secret_binding_validation": secret_validation,
        "secret_binding_metadata_evidence": secret_payload,
        "one_order_guard": one_order_guard,
        "endpoint_adapter_contract": {
            "adapter_id": adapter.adapter_id,
            "venue": adapter.venue,
            "environment": adapter.environment,
            "real_endpoint_adapter": adapter.real_endpoint_adapter,
            "place_order_endpoint_supported_by_contract": adapter.place_order_endpoint_supported_by_contract,
            "order_status_endpoint_supported_by_contract": adapter.order_status_endpoint_supported_by_contract,
            "cancel_endpoint_supported_by_contract": adapter.cancel_endpoint_supported_by_contract,
            "server_time_sync_supported_by_contract": adapter.server_time_sync_supported_by_contract,
            "recv_window_timestamp_supported_by_contract": adapter.recv_window_timestamp_supported_by_contract,
            "hmac_signing_supported_by_contract": adapter.hmac_signing_supported_by_contract,
            "rate_limit_handling_supported_by_contract": adapter.rate_limit_handling_supported_by_contract,
            "actual_network_calls_enabled": False,
        },
        "endpoint_boundary_evidence": {
            "place_order": place_boundary,
            "status_polling": status_boundary,
            "cancel": cancel_boundary,
        },
        "post_submit_relock_policy": {
            "post_submit_relock_required": True,
            "place_order_enabled_after_action": False,
            "cancel_order_enabled_after_action": False,
            "signed_order_executor_enabled_after_action": False,
            "testnet_order_submission_allowed_after_action": False,
            "order_endpoint_call_allowed_after_action": False,
            "signature_creation_allowed_after_action": False,
            "http_request_allowed_after_action": False,
        },
        "session_close_and_reconciliation_boundary": {
            "status_polling_evidence_required_after_real_submit": True,
            "cancel_boundary_evidence_required_after_real_submit": True,
            "signed_testnet_reconciliation_required_after_real_submit": True,
            "signed_testnet_session_close_required_after_real_submit": True,
            "real_exchange_order_id_present": False,
            "actual_exchange_response_present": False,
        },
        "block_reasons": blockers,
        "created_at_utc": created_at_utc,
        **disabled_flags,
    }
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    if report["unsafe_truthy_execution_flags"]:
        report["blocked"] = True
        report["fail_closed"] = True
        report["status"] = STATUS_BLOCKED_REVIEW_ONLY
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P4_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p4_signed_testnet_runtime_package_id"] = stable_id("p4_signed_testnet_runtime_package", report, 24)
    report["p4_signed_testnet_runtime_package_sha256"] = sha256_json(report)
    return report


def build_p4_negative_fixture_results() -> dict[str, Any]:
    base_secret = RuntimeSecretBindingMetadata(secret_reference_id="metadata_only_testnet_key_ref", key_fingerprint_sha256="1" * 64)
    duplicate_key = make_idempotency_key({"fixture": "duplicate"})
    cases = {
        "invalid_secret_fingerprint": {
            "secret": RuntimeSecretBindingMetadata(secret_reference_id="metadata_only_testnet_key_ref", key_fingerprint_sha256="not-a-fingerprint"),
            "intent": OneOrderRuntimeIntent(idempotency_key="invalid_secret_case"),
            "existing": [],
        },
        "duplicate_idempotency": {
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key=duplicate_key),
            "existing": [duplicate_key],
        },
        "hard_cap_exceeded": {
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="hard_cap_case", quantity=1.0, reference_price=50000.0, max_notional=10.0),
            "existing": [],
        },
        "kill_switch_engaged": {
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="kill_switch_case", manual_kill_switch_engaged=True),
            "existing": [],
        },
        "stale_hot_path_risk_gate": {
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="stale_risk_case", hot_path_preorder_risk_gate_fresh=False),
            "existing": [],
        },
        "order_count_already_submitted": {
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="order_count_case", order_count_already_submitted=1),
            "existing": [],
        },
    }
    results: dict[str, Any] = {}
    for name, fixture in cases.items():
        intent = fixture["intent"]
        secret = fixture["secret"]
        idempotency_key = intent.resolved_idempotency_key()
        secret_validation = validate_runtime_secret_binding_metadata(secret)
        one_order_guard = validate_one_order_guard(intent, idempotency_key=idempotency_key, existing_idempotency_keys=fixture["existing"])
        blocked = (not secret_validation["secret_binding_metadata_valid"]) or (not one_order_guard["one_order_guard_passed"])
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": blocked,
            "secret_binding_block_reasons": secret_validation["secret_binding_block_reasons"],
            "one_order_guard_block_reasons": one_order_guard["one_order_guard_block_reasons"],
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        }
    payload = {
        "artifact_type": "p4_signed_testnet_runtime_package_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    payload["negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_signed_testnet_one_order_runtime_package(
    *,
    cfg: AppConfig | None = None,
    intent: OneOrderRuntimeIntent | None = None,
    secret_binding: RuntimeSecretBindingMetadata | Mapping[str, Any] | None = None,
    existing_idempotency_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_signed_testnet_one_order_runtime_package_report(
        cfg=cfg,
        intent=intent,
        secret_binding=secret_binding,
        existing_idempotency_keys=existing_idempotency_keys,
    )
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p4_signed_testnet_runtime_package")
    negative = build_p4_negative_fixture_results()
    registry_record = append_registry_record(
        registry_path(cfg, P4_SIGNED_TESTNET_RUNTIME_PACKAGE_REGISTRY_NAME),
        {
            "artifact_type": "p4_signed_testnet_runtime_package_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "runtime_package_ready_for_separate_operator_submit_action_review_only": report["runtime_package_ready_for_separate_operator_submit_action_review_only"],
            "p4_signed_testnet_runtime_package_id": report["p4_signed_testnet_runtime_package_id"],
            "p4_signed_testnet_runtime_package_sha256": report["p4_signed_testnet_runtime_package_sha256"],
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
            "testnet_order_submission_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        },
        registry_name=P4_SIGNED_TESTNET_RUNTIME_PACKAGE_REGISTRY_NAME,
        id_field="p4_signed_testnet_runtime_package_registry_record_id",
        hash_field="p4_signed_testnet_runtime_package_registry_record_sha256",
        id_prefix="p4_signed_testnet_runtime_package_registry_record",
    )
    report["p4_signed_testnet_runtime_package_registry_record_id"] = registry_record["p4_signed_testnet_runtime_package_registry_record_id"]
    report["p4_signed_testnet_runtime_package_registry_record_sha256"] = registry_record["p4_signed_testnet_runtime_package_registry_record_sha256"]
    report["p4_signed_testnet_runtime_package_sha256"] = sha256_json(report)

    summary = {
        "artifact_type": "p4_signed_testnet_one_order_runtime_package_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "runtime_package_ready_for_separate_operator_submit_action_review_only": report["runtime_package_ready_for_separate_operator_submit_action_review_only"],
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "testnet_order_submission_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "p4_signed_testnet_runtime_package_id": report["p4_signed_testnet_runtime_package_id"],
        "p4_signed_testnet_runtime_package_sha256": report["p4_signed_testnet_runtime_package_sha256"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p4_summary_sha256"] = sha256_json(summary)

    for path in [
        latest / "p4_signed_testnet_one_order_runtime_package_report.json",
        storage / "p4_signed_testnet_one_order_runtime_package_report.json",
    ]:
        atomic_write_json(path, report)
    atomic_write_json(latest / "p4_signed_testnet_runtime_package_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p4_signed_testnet_one_order_runtime_package_registry_record.json", registry_record)
    atomic_write_json(latest / "p4_signed_testnet_one_order_runtime_package_summary.json", summary)
    return report
