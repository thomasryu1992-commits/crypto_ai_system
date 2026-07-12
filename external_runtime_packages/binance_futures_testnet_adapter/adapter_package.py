from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

P59_EXTERNAL_ADAPTER_PACKAGE_VERSION = "p59_binance_futures_testnet_external_adapter_package_v1"
STATUS_PACKAGE_VALIDATED_ADAPTER_DISABLED = (
    "P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED"
)
STATUS_PACKAGE_BLOCKED_FAIL_CLOSED = (
    "P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_BLOCKED_FAIL_CLOSED"
)

ALLOWED_TESTNET_REST_BASE_URL = "https://demo-fapi.binance.com"
ALLOWED_ENVIRONMENT = "testnet"
ALLOWED_VENUE = "binance_futures_testnet"
ALLOWED_SYMBOL = "BTCUSDT"
ALLOWED_ENDPOINTS: dict[str, str] = {
    "submit": "/fapi/v1/order",
    "status": "/fapi/v1/order",
    "cancel": "/fapi/v1/order",
    "test_submit": "/fapi/v1/order/test",
}
ALLOWED_METHODS: dict[str, str] = {
    "submit": "POST",
    "status": "GET",
    "cancel": "DELETE",
    "test_submit": "POST",
}
FORBIDDEN_ENDPOINT_TOKENS = (
    "leverage",
    "marginType",
    "positionMargin",
    "multiAssetsMargin",
    "withdraw",
    "transfer",
    "apiRestrictions",
    "commissionRate",
    "listenKey",
)
FORBIDDEN_SECRET_FIELD_TOKENS = (
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_secret",
    "secret_file_contents",
    "raw_signed_payload",
    "raw_request_body",
    "unredacted_exchange_response",
)


class AdapterPackageError(RuntimeError):
    """Base fail-closed error for the P59 external adapter package."""


class AdapterPackageDisabledError(AdapterPackageError):
    """Raised when a disabled network, signing, or submit path is invoked."""


class AdapterPackageValidationError(AdapterPackageError):
    """Raised when package, policy, request, or metadata validation fails."""


class ExternalProcessMemorySigner(Protocol):
    """External signer contract only; no signer implementation is bundled."""

    signer_id: str
    process_memory_only: bool
    secret_persistence_allowed: bool
    secret_logging_allowed: bool

    def sign_request_digest(
        self,
        *,
        unsigned_request_digest_sha256: str,
        secret_reference_id: str,
    ) -> Mapping[str, Any]:
        ...


class ExternalHttpTransport(Protocol):
    """External transport contract only; no HTTP implementation is bundled."""

    transport_id: str
    testnet_only: bool
    base_url: str

    def send_redacted_request(self, request_metadata: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


def _sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _verify_embedded_hash(payload: Mapping[str, Any] | None, hash_key: str) -> bool:
    obj = dict(payload or {})
    expected = str(obj.pop(hash_key, "") or "").strip().lower()
    return _is_sha256_hex(expected) and _sha256_json(obj) == expected


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            key_l = str(key).lower()
            if any(token in key_l for token in FORBIDDEN_SECRET_FIELD_TOKENS):
                safe_boolean = isinstance(value, bool) and any(
                    marker in key_l
                    for marker in ("_included", "_accessed", "_logged", "_created", "_allowed")
                )
                if not safe_boolean:
                    blockers.append(f"P59_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, prefix=child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
    return blockers


@dataclass(frozen=True)
class BinanceFuturesTestnetEndpointPolicy:
    policy_version: str = "p59_binance_futures_testnet_endpoint_policy_v1"
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    rest_base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    symbol_allowlist: tuple[str, ...] = (ALLOWED_SYMBOL,)
    submit_method: str = "POST"
    submit_path: str = ALLOWED_ENDPOINTS["submit"]
    status_method: str = "GET"
    status_path: str = ALLOWED_ENDPOINTS["status"]
    cancel_method: str = "DELETE"
    cancel_path: str = ALLOWED_ENDPOINTS["cancel"]
    test_submit_method: str = "POST"
    test_submit_path: str = ALLOWED_ENDPOINTS["test_submit"]
    max_order_count: int = 1
    max_notional_usdt: str = "10.00"
    min_notional_must_be_venue_validated_at_runtime: bool = True
    mainnet_base_url_allowed: bool = False
    arbitrary_endpoint_allowed: bool = False
    leverage_mutation_allowed: bool = False
    margin_mutation_allowed: bool = False
    position_margin_mutation_allowed: bool = False
    transfer_allowed: bool = False
    withdrawal_allowed: bool = False
    admin_permission_allowed: bool = False
    live_endpoint_allowed: bool = False
    fail_closed_on_unknown_endpoint: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["symbol_allowlist"] = list(self.symbol_allowlist)
        payload["p59_endpoint_policy_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class MetadataOnlyKeyBinding:
    binding_version: str = "p59_metadata_only_key_binding_v1"
    secret_reference_id: str = "OPERATOR_SUPPLIED_TESTNET_SECRET_REFERENCE_ID"
    key_fingerprint_sha256: str = "0" * 64
    api_key_fingerprint_sha256: str = "0" * 64
    binding_mode: str = "metadata_reference_only"
    signer_location: str = "external_runtime_process_memory_only"
    key_scope: str = "binance_futures_testnet_trade_only_no_withdrawal"
    testnet_only: bool = True
    withdrawal_permission_expected: bool = False
    transfer_permission_expected: bool = False
    admin_permission_expected: bool = False
    live_or_mainnet_scope_expected: bool = False
    raw_key_value_included: bool = False
    raw_secret_value_included: bool = False
    secret_file_path_included: bool = False
    secret_file_read_allowed: bool = False
    secret_value_persistence_allowed: bool = False
    secret_value_logging_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p59_metadata_only_key_binding_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class DisabledExternalAdapterRunnerConfig:
    runner_version: str = "p59_disabled_external_adapter_runner_v1"
    package_scope: str = "separate_external_runtime_package_only"
    external_runtime_only: bool = True
    review_package_may_import_runner: bool = False
    runner_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    submit_enabled: bool = False
    status_polling_enabled: bool = False
    cancel_enabled: bool = False
    real_adapter_attached: bool = False
    external_signer_attached: bool = False
    external_transport_attached: bool = False
    max_order_count: int = 1
    require_exact_operator_arming_phrase: bool = True
    require_p6_preflight: bool = True
    require_p54_final_guard: bool = True
    require_hot_path_risk_gate: bool = True
    require_idempotency_key: bool = True
    require_duplicate_submit_lock: bool = True
    require_post_submit_relock: bool = True
    require_redacted_evidence_export: bool = True
    require_no_secret_log_scan: bool = True
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p59_disabled_runner_config_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class ExternalAdapterPackageManifest:
    manifest_version: str = "p59_external_adapter_package_manifest_v1"
    package_id: str = "binance_futures_testnet_external_adapter_package"
    package_version: str = P59_EXTERNAL_ADAPTER_PACKAGE_VERSION
    package_scope: str = "separate_external_runtime_package_only"
    external_runtime_only: bool = True
    included_in_default_runtime_candidate: bool = False
    review_package_import_allowed: bool = False
    adapter_orchestration_implemented: bool = True
    endpoint_policy_implemented: bool = True
    metadata_only_key_binding_implemented: bool = True
    process_memory_signer_protocol_implemented: bool = True
    external_transport_protocol_implemented: bool = True
    concrete_network_transport_implementation_included: bool = False
    concrete_signer_implementation_included: bool = False
    secret_reader_implementation_included: bool = False
    real_endpoint_call_implementation_enabled: bool = False
    disabled_by_default: bool = True
    testnet_only: bool = True
    venue: str = ALLOWED_VENUE
    environment: str = ALLOWED_ENVIRONMENT
    symbol: str = ALLOWED_SYMBOL
    max_order_count: int = 1
    endpoint_policy_ref: str = "BinanceFuturesTestnetEndpointPolicy"
    key_binding_ref: str = "MetadataOnlyKeyBinding"
    signer_protocol_ref: str = "ExternalProcessMemorySigner"
    transport_protocol_ref: str = "ExternalHttpTransport"
    runner_config_ref: str = "DisabledExternalAdapterRunnerConfig"
    package_source_sha256: str = "0" * 64
    order_submission_performed: bool = False
    endpoint_call_performed: bool = False
    signature_created: bool = False
    secret_value_accessed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p59_external_adapter_package_manifest_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P59NoNetworkOrderIntent:
    intent_version: str = "p59_no_network_order_intent_v1"
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    symbol: str = ALLOWED_SYMBOL
    side: str = "BUY"
    order_type: str = "MARKET"
    notional_usdt: str = "5.00"
    quantity: str = "VENUE_FILTER_DERIVED_AT_RUNTIME"
    client_order_id: str = "P59_NO_NETWORK_FIXTURE_CLIENT_ORDER_ID"
    idempotency_key: str = "1" * 64
    hot_path_risk_gate_id: str = "P59_FIXTURE_HOT_PATH_RISK_GATE_ID"
    hot_path_risk_gate_sha256: str = "2" * 64
    fixture_only: bool = True
    submit_requested: bool = False
    network_call_requested: bool = False
    signature_requested: bool = False
    runtime_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p59_no_network_order_intent_sha256"] = _sha256_json(payload)
        return payload


def validate_endpoint_policy(policy: Mapping[str, Any] | BinanceFuturesTestnetEndpointPolicy | None) -> dict[str, Any]:
    payload = policy.to_dict() if isinstance(policy, BinanceFuturesTestnetEndpointPolicy) else dict(policy or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p59_endpoint_policy_sha256"):
        blockers.append("P59_ENDPOINT_POLICY_EMBEDDED_SHA256_INVALID")
    if payload.get("environment") != ALLOWED_ENVIRONMENT:
        blockers.append("P59_ENDPOINT_POLICY_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") != ALLOWED_VENUE:
        blockers.append("P59_ENDPOINT_POLICY_VENUE_INVALID")
    if payload.get("rest_base_url") != ALLOWED_TESTNET_REST_BASE_URL:
        blockers.append("P59_ENDPOINT_POLICY_BASE_URL_NOT_ALLOWED_TESTNET")
    if payload.get("symbol_allowlist") != [ALLOWED_SYMBOL]:
        blockers.append("P59_ENDPOINT_POLICY_SYMBOL_ALLOWLIST_INVALID")
    for name in ("submit", "status", "cancel", "test_submit"):
        if payload.get(f"{name}_path") != ALLOWED_ENDPOINTS[name]:
            blockers.append(f"P59_ENDPOINT_POLICY_{name.upper()}_PATH_INVALID")
        if payload.get(f"{name}_method") != ALLOWED_METHODS[name]:
            blockers.append(f"P59_ENDPOINT_POLICY_{name.upper()}_METHOD_INVALID")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P59_ENDPOINT_POLICY_MAX_ORDER_COUNT_NOT_ONE")
    for key in (
        "min_notional_must_be_venue_validated_at_runtime",
        "fail_closed_on_unknown_endpoint",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P59_ENDPOINT_POLICY_{key.upper()}_NOT_TRUE")
    for key in (
        "mainnet_base_url_allowed",
        "arbitrary_endpoint_allowed",
        "leverage_mutation_allowed",
        "margin_mutation_allowed",
        "position_margin_mutation_allowed",
        "transfer_allowed",
        "withdrawal_allowed",
        "admin_permission_allowed",
        "live_endpoint_allowed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P59_ENDPOINT_POLICY_{key.upper()}_NOT_FALSE")
    for key, value in payload.items():
        if key.endswith("_path") and any(token.lower() in str(value).lower() for token in FORBIDDEN_ENDPOINT_TOKENS):
            blockers.append(f"P59_FORBIDDEN_ENDPOINT_PATH:{key}")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "endpoint_policy_valid": not blockers,
        "endpoint_policy_block_reasons": sorted(dict.fromkeys(blockers)),
        "testnet_base_url_pinned": payload.get("rest_base_url") == ALLOWED_TESTNET_REST_BASE_URL,
        "only_btcusdt_allowed": payload.get("symbol_allowlist") == [ALLOWED_SYMBOL],
    }
    validation["p59_endpoint_policy_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_metadata_only_key_binding(binding: Mapping[str, Any] | MetadataOnlyKeyBinding | None) -> dict[str, Any]:
    payload = binding.to_dict() if isinstance(binding, MetadataOnlyKeyBinding) else dict(binding or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p59_metadata_only_key_binding_sha256"):
        blockers.append("P59_KEY_BINDING_EMBEDDED_SHA256_INVALID")
    if not str(payload.get("secret_reference_id") or "").strip():
        blockers.append("P59_SECRET_REFERENCE_ID_MISSING")
    if not _is_sha256_hex(payload.get("key_fingerprint_sha256")):
        blockers.append("P59_KEY_FINGERPRINT_SHA256_INVALID")
    if not _is_sha256_hex(payload.get("api_key_fingerprint_sha256")):
        blockers.append("P59_API_KEY_FINGERPRINT_SHA256_INVALID")
    if payload.get("binding_mode") != "metadata_reference_only":
        blockers.append("P59_KEY_BINDING_MODE_INVALID")
    if payload.get("signer_location") != "external_runtime_process_memory_only":
        blockers.append("P59_SIGNER_LOCATION_INVALID")
    if payload.get("testnet_only") is not True:
        blockers.append("P59_KEY_BINDING_TESTNET_ONLY_NOT_TRUE")
    for key in (
        "withdrawal_permission_expected",
        "transfer_permission_expected",
        "admin_permission_expected",
        "live_or_mainnet_scope_expected",
        "raw_key_value_included",
        "raw_secret_value_included",
        "secret_file_path_included",
        "secret_file_read_allowed",
        "secret_value_persistence_allowed",
        "secret_value_logging_allowed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P59_KEY_BINDING_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "metadata_only_key_binding_valid": not blockers,
        "metadata_only_key_binding_block_reasons": sorted(dict.fromkeys(blockers)),
        "raw_key_or_secret_present": payload.get("raw_key_value_included") is True or payload.get("raw_secret_value_included") is True,
        "process_memory_only_signing_boundary": payload.get("signer_location") == "external_runtime_process_memory_only",
    }
    validation["p59_metadata_only_key_binding_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_disabled_runner_config(config: Mapping[str, Any] | DisabledExternalAdapterRunnerConfig | None) -> dict[str, Any]:
    payload = config.to_dict() if isinstance(config, DisabledExternalAdapterRunnerConfig) else dict(config or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p59_disabled_runner_config_sha256"):
        blockers.append("P59_RUNNER_CONFIG_EMBEDDED_SHA256_INVALID")
    for key in (
        "external_runtime_only",
        "require_exact_operator_arming_phrase",
        "require_p6_preflight",
        "require_p54_final_guard",
        "require_hot_path_risk_gate",
        "require_idempotency_key",
        "require_duplicate_submit_lock",
        "require_post_submit_relock",
        "require_redacted_evidence_export",
        "require_no_secret_log_scan",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P59_RUNNER_CONFIG_{key.upper()}_NOT_TRUE")
    for key in (
        "review_package_may_import_runner",
        "runner_enabled",
        "network_calls_enabled",
        "signing_enabled",
        "submit_enabled",
        "status_polling_enabled",
        "cancel_enabled",
        "real_adapter_attached",
        "external_signer_attached",
        "external_transport_attached",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P59_RUNNER_CONFIG_{key.upper()}_NOT_FALSE")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P59_RUNNER_CONFIG_MAX_ORDER_COUNT_NOT_ONE")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "disabled_runner_config_valid": not blockers,
        "disabled_runner_config_block_reasons": sorted(dict.fromkeys(blockers)),
        "runner_enabled": payload.get("runner_enabled") is True,
        "network_calls_enabled": payload.get("network_calls_enabled") is True,
        "submit_enabled": payload.get("submit_enabled") is True,
    }
    validation["p59_disabled_runner_config_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_adapter_package_manifest(manifest: Mapping[str, Any] | ExternalAdapterPackageManifest | None) -> dict[str, Any]:
    payload = manifest.to_dict() if isinstance(manifest, ExternalAdapterPackageManifest) else dict(manifest or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p59_external_adapter_package_manifest_sha256"):
        blockers.append("P59_PACKAGE_MANIFEST_EMBEDDED_SHA256_INVALID")
    if payload.get("package_scope") != "separate_external_runtime_package_only":
        blockers.append("P59_PACKAGE_SCOPE_INVALID")
    for key in (
        "external_runtime_only",
        "adapter_orchestration_implemented",
        "endpoint_policy_implemented",
        "metadata_only_key_binding_implemented",
        "process_memory_signer_protocol_implemented",
        "external_transport_protocol_implemented",
        "disabled_by_default",
        "testnet_only",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P59_PACKAGE_MANIFEST_{key.upper()}_NOT_TRUE")
    for key in (
        "included_in_default_runtime_candidate",
        "review_package_import_allowed",
        "concrete_network_transport_implementation_included",
        "concrete_signer_implementation_included",
        "secret_reader_implementation_included",
        "real_endpoint_call_implementation_enabled",
        "order_submission_performed",
        "endpoint_call_performed",
        "signature_created",
        "secret_value_accessed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P59_PACKAGE_MANIFEST_{key.upper()}_NOT_FALSE")
    if payload.get("environment") != ALLOWED_ENVIRONMENT:
        blockers.append("P59_PACKAGE_MANIFEST_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") != ALLOWED_VENUE:
        blockers.append("P59_PACKAGE_MANIFEST_VENUE_INVALID")
    if payload.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P59_PACKAGE_MANIFEST_SYMBOL_INVALID")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P59_PACKAGE_MANIFEST_MAX_ORDER_COUNT_NOT_ONE")
    if not _is_sha256_hex(payload.get("package_source_sha256")):
        blockers.append("P59_PACKAGE_SOURCE_SHA256_INVALID")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "adapter_package_manifest_valid": not blockers,
        "adapter_package_manifest_block_reasons": sorted(dict.fromkeys(blockers)),
        "separate_external_runtime_package_only": payload.get("package_scope") == "separate_external_runtime_package_only",
        "included_in_default_runtime_candidate": payload.get("included_in_default_runtime_candidate") is True,
        "real_endpoint_call_implementation_enabled": payload.get("real_endpoint_call_implementation_enabled") is True,
    }
    validation["p59_adapter_package_manifest_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_order_intent(intent: Mapping[str, Any] | P59NoNetworkOrderIntent | None) -> dict[str, Any]:
    payload = intent.to_dict() if isinstance(intent, P59NoNetworkOrderIntent) else dict(intent or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p59_no_network_order_intent_sha256"):
        blockers.append("P59_ORDER_INTENT_EMBEDDED_SHA256_INVALID")
    if payload.get("environment") != ALLOWED_ENVIRONMENT:
        blockers.append("P59_ORDER_INTENT_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") != ALLOWED_VENUE:
        blockers.append("P59_ORDER_INTENT_VENUE_INVALID")
    if payload.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P59_ORDER_INTENT_SYMBOL_INVALID")
    if payload.get("side") not in {"BUY", "SELL"}:
        blockers.append("P59_ORDER_INTENT_SIDE_INVALID")
    if payload.get("order_type") not in {"MARKET", "LIMIT"}:
        blockers.append("P59_ORDER_INTENT_TYPE_INVALID")
    if not _is_sha256_hex(payload.get("idempotency_key")):
        blockers.append("P59_ORDER_INTENT_IDEMPOTENCY_KEY_INVALID")
    if not str(payload.get("hot_path_risk_gate_id") or "").strip():
        blockers.append("P59_ORDER_INTENT_HOT_PATH_RISK_GATE_ID_MISSING")
    if not _is_sha256_hex(payload.get("hot_path_risk_gate_sha256")):
        blockers.append("P59_ORDER_INTENT_HOT_PATH_RISK_GATE_SHA256_INVALID")
    if payload.get("fixture_only") is not True:
        blockers.append("P59_ORDER_INTENT_FIXTURE_ONLY_NOT_TRUE")
    for key in ("submit_requested", "network_call_requested", "signature_requested", "runtime_authority_granted"):
        if payload.get(key) is not False:
            blockers.append(f"P59_ORDER_INTENT_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "order_intent_valid": not blockers,
        "order_intent_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": payload.get("fixture_only") is True,
        "submit_requested": payload.get("submit_requested") is True,
    }
    validation["p59_order_intent_validation_sha256"] = _sha256_json(validation)
    return validation


class BinanceFuturesTestnetAdapterSkeleton:
    """Policy-bound adapter orchestration with no network, signer, or secret implementation."""

    adapter_id = "p59_binance_futures_testnet_adapter_skeleton"
    adapter_version = P59_EXTERNAL_ADAPTER_PACKAGE_VERSION
    venue = ALLOWED_VENUE
    environment = ALLOWED_ENVIRONMENT
    symbol = ALLOWED_SYMBOL
    real_endpoint_adapter = False
    concrete_network_transport_included = False
    concrete_signer_included = False
    network_call_capable = False
    submit_enabled_by_default = False

    def __init__(
        self,
        *,
        endpoint_policy: BinanceFuturesTestnetEndpointPolicy | None = None,
        key_binding: MetadataOnlyKeyBinding | None = None,
        runner_config: DisabledExternalAdapterRunnerConfig | None = None,
    ) -> None:
        self.endpoint_policy = endpoint_policy or BinanceFuturesTestnetEndpointPolicy()
        self.key_binding = key_binding or MetadataOnlyKeyBinding(
            key_fingerprint_sha256=_sha256_json({"p59": "metadata-only-key-fingerprint"}),
            api_key_fingerprint_sha256=_sha256_json({"p59": "metadata-only-api-key-fingerprint"}),
        )
        self.runner_config = runner_config or DisabledExternalAdapterRunnerConfig()

    def build_unsigned_request_plan(self, intent: Mapping[str, Any] | P59NoNetworkOrderIntent) -> dict[str, Any]:
        intent_payload = intent.to_dict() if isinstance(intent, P59NoNetworkOrderIntent) else dict(intent)
        validations = {
            "endpoint_policy": validate_endpoint_policy(self.endpoint_policy),
            "key_binding": validate_metadata_only_key_binding(self.key_binding),
            "runner_config": validate_disabled_runner_config(self.runner_config),
            "order_intent": validate_order_intent(intent_payload),
        }
        blockers: list[str] = []
        for item in validations.values():
            for key, value in item.items():
                if key.endswith("_block_reasons") and isinstance(value, list):
                    blockers.extend(value)
        if blockers:
            raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(blockers))))
        plan = {
            "artifact_type": "p59_unsigned_request_plan_no_network_no_signature",
            "environment": ALLOWED_ENVIRONMENT,
            "venue": ALLOWED_VENUE,
            "base_url": ALLOWED_TESTNET_REST_BASE_URL,
            "method": "POST",
            "path": ALLOWED_ENDPOINTS["submit"],
            "symbol": ALLOWED_SYMBOL,
            "side": intent_payload["side"],
            "order_type": intent_payload["order_type"],
            "notional_usdt": intent_payload["notional_usdt"],
            "quantity_source": "VENUE_FILTER_DERIVED_AT_RUNTIME_AFTER_FRESH_VALIDATION",
            "client_order_id": intent_payload["client_order_id"],
            "idempotency_key": intent_payload["idempotency_key"],
            "hot_path_risk_gate_id": intent_payload["hot_path_risk_gate_id"],
            "hot_path_risk_gate_sha256": intent_payload["hot_path_risk_gate_sha256"],
            "secret_reference_id": self.key_binding.secret_reference_id,
            "key_fingerprint_sha256": self.key_binding.key_fingerprint_sha256,
            "signing_boundary": self.key_binding.signer_location,
            "signer_attached": False,
            "transport_attached": False,
            "network_call_allowed": False,
            "submit_allowed": False,
            "raw_request_body_created": False,
            "signed_request_created": False,
            "signature_created": False,
            "http_request_sent": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        }
        plan["p59_unsigned_request_plan_sha256"] = _sha256_json(plan)
        return plan

    def execute_no_network_contract_self_test(self, intent: Mapping[str, Any] | P59NoNetworkOrderIntent | None = None) -> dict[str, Any]:
        intent_obj = intent or P59NoNetworkOrderIntent()
        plan = self.build_unsigned_request_plan(intent_obj)
        result = {
            "artifact_type": "p59_no_network_adapter_package_self_test_result",
            "adapter_skeleton_instantiated": True,
            "endpoint_policy_validated": True,
            "metadata_only_key_binding_validated": True,
            "disabled_runner_config_validated": True,
            "unsigned_request_plan_built": True,
            "unsigned_request_plan_sha256": plan["p59_unsigned_request_plan_sha256"],
            "real_endpoint_adapter": False,
            "concrete_network_transport_included": False,
            "concrete_signer_included": False,
            "runner_enabled": False,
            "network_calls_enabled": False,
            "signing_enabled": False,
            "submit_enabled": False,
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "runtime_authority_granted": False,
        }
        result["p59_no_network_adapter_package_self_test_result_sha256"] = _sha256_json(result)
        return result

    def execute_real_signed_testnet_order(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        del args, kwargs
        raise AdapterPackageDisabledError(
            "P59_REAL_SIGNED_TESTNET_ADAPTER_EXECUTION_DISABLED_PENDING_SEPARATE_OPERATOR_APPROVAL_EXTERNAL_SIGNER_AND_EXTERNAL_TRANSPORT"
        )


def calculate_package_source_sha256(package_dir: str | Path | None = None) -> str:
    base = Path(package_dir) if package_dir is not None else Path(__file__).resolve().parent
    items: list[dict[str, str]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo", ".zip"}:
            continue
        rel = path.relative_to(base).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        items.append({"path": rel, "sha256": digest})
    return _sha256_json(items)


def build_p59_no_network_package_self_test() -> dict[str, Any]:
    adapter = BinanceFuturesTestnetAdapterSkeleton()
    result = adapter.execute_no_network_contract_self_test()
    real_path_blocked = False
    try:
        adapter.execute_real_signed_testnet_order()
    except AdapterPackageDisabledError:
        real_path_blocked = True
    report = {
        "artifact_type": "p59_no_network_external_adapter_package_self_test_report",
        "self_test_passed": all(
            (
                result["adapter_skeleton_instantiated"],
                result["endpoint_policy_validated"],
                result["metadata_only_key_binding_validated"],
                result["disabled_runner_config_validated"],
                result["unsigned_request_plan_built"],
                real_path_blocked,
                result["actual_order_submission_performed"] is False,
                result["http_request_sent"] is False,
                result["signature_created"] is False,
                result["secret_value_accessed"] is False,
            )
        ),
        "real_execution_path_blocked": real_path_blocked,
        **result,
    }
    report["p59_no_network_external_adapter_package_self_test_report_sha256"] = _sha256_json(report)
    return report


def build_p59_negative_fixture_results() -> dict[str, Any]:
    fixtures: dict[str, dict[str, Any]] = {}

    endpoint_cases = {
        "mainnet_base_url": replace(BinanceFuturesTestnetEndpointPolicy(), rest_base_url="https://fapi.binance.com").to_dict(),
        "eth_symbol": replace(BinanceFuturesTestnetEndpointPolicy(), symbol_allowlist=("ETHUSDT",)).to_dict(),
        "leverage_path": replace(BinanceFuturesTestnetEndpointPolicy(), submit_path="/fapi/v1/leverage").to_dict(),
    }
    for name, payload in endpoint_cases.items():
        fixtures[name] = validate_endpoint_policy(payload)

    key_cases = {
        "raw_secret_included": replace(MetadataOnlyKeyBinding(), raw_secret_value_included=True).to_dict(),
        "secret_file_read_allowed": replace(MetadataOnlyKeyBinding(), secret_file_read_allowed=True).to_dict(),
    }
    for name, payload in key_cases.items():
        fixtures[name] = validate_metadata_only_key_binding(payload)

    runner_cases = {
        "runner_enabled": replace(DisabledExternalAdapterRunnerConfig(), runner_enabled=True).to_dict(),
        "network_calls_enabled": replace(DisabledExternalAdapterRunnerConfig(), network_calls_enabled=True).to_dict(),
        "submit_enabled": replace(DisabledExternalAdapterRunnerConfig(), submit_enabled=True).to_dict(),
    }
    for name, payload in runner_cases.items():
        fixtures[name] = validate_disabled_runner_config(payload)

    source_sha = calculate_package_source_sha256()
    manifest_cases = {
        "included_in_runtime_candidate": replace(ExternalAdapterPackageManifest(package_source_sha256=source_sha), included_in_default_runtime_candidate=True).to_dict(),
        "real_transport_included": replace(ExternalAdapterPackageManifest(package_source_sha256=source_sha), concrete_network_transport_implementation_included=True).to_dict(),
    }
    for name, payload in manifest_cases.items():
        fixtures[name] = validate_adapter_package_manifest(payload)

    def blocked(item: Mapping[str, Any]) -> bool:
        valid_values = [value for key, value in item.items() if key.endswith("_valid")]
        return bool(valid_values) and all(value is False for value in valid_values)

    report = {
        "artifact_type": "p59_external_adapter_package_negative_fixture_results",
        "fixture_results": fixtures,
        "fixture_count": len(fixtures),
        "all_negative_fixtures_blocked_fail_closed": all(blocked(item) for item in fixtures.values()),
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
    }
    report["p59_external_adapter_package_negative_fixture_results_sha256"] = _sha256_json(report)
    return report


def build_p59_adapter_package_report() -> dict[str, Any]:
    source_sha = calculate_package_source_sha256()
    policy = BinanceFuturesTestnetEndpointPolicy().to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256=_sha256_json({"p59": "metadata-only-key-fingerprint"}),
        api_key_fingerprint_sha256=_sha256_json({"p59": "metadata-only-api-key-fingerprint"}),
    ).to_dict()
    runner = DisabledExternalAdapterRunnerConfig().to_dict()
    manifest = ExternalAdapterPackageManifest(package_source_sha256=source_sha).to_dict()
    policy_validation = validate_endpoint_policy(policy)
    key_validation = validate_metadata_only_key_binding(key_binding)
    runner_validation = validate_disabled_runner_config(runner)
    manifest_validation = validate_adapter_package_manifest(manifest)
    self_test = build_p59_no_network_package_self_test()
    negatives = build_p59_negative_fixture_results()
    blockers: list[str] = []
    for item in (policy_validation, key_validation, runner_validation, manifest_validation):
        for key, value in item.items():
            if key.endswith("_block_reasons") and isinstance(value, list):
                blockers.extend(value)
    if not self_test["self_test_passed"]:
        blockers.append("P59_NO_NETWORK_PACKAGE_SELF_TEST_FAILED")
    if not negatives["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("P59_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    status = STATUS_PACKAGE_BLOCKED_FAIL_CLOSED if blockers else STATUS_PACKAGE_VALIDATED_ADAPTER_DISABLED
    report = {
        "artifact_type": "p59_separate_testnet_external_adapter_package_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "package_version": P59_EXTERNAL_ADAPTER_PACKAGE_VERSION,
        "package_source_sha256": source_sha,
        "endpoint_policy": policy,
        "metadata_only_key_binding": key_binding,
        "disabled_runner_config": runner,
        "adapter_package_manifest": manifest,
        "endpoint_policy_validation": policy_validation,
        "metadata_only_key_binding_validation": key_validation,
        "disabled_runner_config_validation": runner_validation,
        "adapter_package_manifest_validation": manifest_validation,
        "no_network_package_self_test": self_test,
        "negative_fixture_results": negatives,
        "separate_external_runtime_package_created": True,
        "included_in_default_runtime_candidate": False,
        "adapter_orchestration_implemented": True,
        "concrete_network_transport_implementation_included": False,
        "concrete_signer_implementation_included": False,
        "secret_reader_implementation_included": False,
        "real_endpoint_call_implementation_enabled": False,
        "external_runtime_runner_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "submit_enabled": False,
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        "actual_order_submission_performed": False,
        "actual_testnet_order_submitted": False,
        "actual_live_order_submitted": False,
        "external_order_submission_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "runtime_authority_granted": False,
        "runtime_mutation_performed": False,
        "runtime_scheduler_enabled": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }
    report["p59_separate_testnet_external_adapter_package_sha256"] = _sha256_json(report)
    return report
