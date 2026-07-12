from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlencode

from .adapter_package import (
    ALLOWED_ENDPOINTS,
    ALLOWED_ENVIRONMENT,
    ALLOWED_METHODS,
    ALLOWED_SYMBOL,
    ALLOWED_TESTNET_REST_BASE_URL,
    ALLOWED_VENUE,
    AdapterPackageDisabledError,
    AdapterPackageValidationError,
    MetadataOnlyKeyBinding,
    _is_sha256_hex,
    _sha256_json,
    _verify_embedded_hash,
    validate_metadata_only_key_binding,
)

P61_REAL_ORDER_TEST_DRY_VALIDATION_ADAPTER_VERSION = "p61_real_testnet_order_test_dry_validation_adapter_v1"
STATUS_ADAPTER_VALIDATED_DISABLED = (
    "P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_ADAPTER_BLOCKED_FAIL_CLOSED = (
    "P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_BLOCKED_FAIL_CLOSED"
)

EXACT_ORDER_TEST_APPROVAL_PHRASE = (
    "AUTHORIZE ONE BINANCE FUTURES TESTNET ORDER TEST DRY VALIDATION ONLY"
)
ALLOWED_REAL_ORDER_TEST_SCOPE = "p61_approved_external_runtime_order_test_only"
NO_NETWORK_SELF_TEST_SCOPE = "p61_no_network_injected_executor_self_test"


class P61ExternalSignedOrderTestExecutor(Protocol):
    """External component contract.

    Credential values, signing, and HTTP headers remain inside the external process.
    This package passes only a metadata reference and a canonical request descriptor.
    """

    executor_id: str
    external_runtime_only: bool
    concrete_external_component: bool
    testnet_only: bool
    base_url: str
    method: str
    path: str
    process_memory_credential_binding: bool
    credential_persistence_allowed: bool
    credential_logging_allowed: bool
    raw_credential_exposed_to_adapter: bool
    network_send_capable: bool

    def execute_signed_order_test(
        self,
        *,
        request_descriptor: Mapping[str, Any],
        credential_reference_id: str,
    ) -> Mapping[str, Any]:
        ...


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_l = str(key).lower()
            child = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, bool):
                continue
            if any(
                token in key_l
                for token in (
                    "api_key_value",
                    "api_secret_value",
                    "secret_value",
                    "private_key",
                    "passphrase",
                    "raw_secret",
                    "raw_signed_payload",
                    "raw_request_body",
                    "unredacted_exchange_response",
                    "credential_value",
                )
            ):
                blockers.append(f"P61_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, prefix=child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
    return blockers


def _collect_blockers(*validations: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for validation in validations:
        for key, value in validation.items():
            if key.endswith("_block_reasons") and isinstance(value, list):
                blockers.extend(str(item) for item in value)
    return sorted(dict.fromkeys(blockers))


def _positive_decimal(value: Any) -> bool:
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, ValueError, TypeError):
        return False


@dataclass(frozen=True)
class P61OrderTestAdapterPolicy:
    policy_version: str = "p61_order_test_adapter_policy_v1"
    package_scope: str = "separate_external_runtime_package_only"
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    symbol: str = ALLOWED_SYMBOL
    max_request_count: int = 1
    max_recv_window_ms: int = 5000
    separate_operator_approval_required: bool = True
    external_process_memory_credential_binding_required: bool = True
    redacted_response_required: bool = True
    no_secret_log_scan_required: bool = True
    adapter_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    real_order_test_call_enabled: bool = False
    real_order_submit_endpoint_enabled: bool = False
    status_endpoint_enabled: bool = False
    cancel_endpoint_enabled: bool = False
    mainnet_allowed: bool = False
    arbitrary_endpoint_allowed: bool = False
    raw_request_persistence_allowed: bool = False
    raw_response_persistence_allowed: bool = False
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p61_order_test_adapter_policy_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P61ExternalExecutorMetadata:
    metadata_version: str = "p61_external_signed_order_test_executor_metadata_v1"
    executor_id: str = "OPERATOR_SUPPLIED_EXTERNAL_SIGNED_ORDER_TEST_EXECUTOR"
    external_runtime_only: bool = True
    concrete_external_component: bool = True
    testnet_only: bool = True
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    process_memory_credential_binding: bool = True
    credential_reference_id_required: bool = True
    key_fingerprint_sha256_required: bool = True
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    raw_credential_exposed_to_adapter: bool = False
    redacted_response_only: bool = True
    network_send_capable: bool = True
    included_in_review_package: bool = False
    included_in_default_runtime_candidate: bool = False
    call_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p61_external_executor_metadata_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P61OperatorOrderTestApproval:
    approval_version: str = "p61_operator_order_test_approval_v1"
    approval_scope: str = "p61_order_test_dry_validation_only"
    exact_approval_phrase: str = ""
    operator_confirmation_sha256: str = "0" * 64
    source_p60_report_sha256: str = "0" * 64
    request_descriptor_sha256: str = "0" * 64
    credential_reference_id: str = "OPERATOR_SUPPLIED_TESTNET_CREDENTIAL_REFERENCE_ID"
    key_fingerprint_sha256: str = "0" * 64
    approval_granted: bool = False
    fixture_only: bool = False
    one_request_only: bool = True
    testnet_only: bool = True
    order_test_only: bool = True
    real_order_submit_allowed: bool = False
    status_polling_allowed: bool = False
    cancel_allowed: bool = False
    runtime_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p61_operator_order_test_approval_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P61OrderTestRequestDescriptor:
    descriptor_version: str = "p61_order_test_request_descriptor_v1"
    execution_scope: str = NO_NETWORK_SELF_TEST_SCOPE
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    symbol: str = ALLOWED_SYMBOL
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: str = "0.001"
    new_client_order_id: str = "P61_ORDER_TEST_SELF_TEST"
    recv_window_ms: int = 5000
    timestamp_ms: int = 1700000000000
    idempotency_key: str = "6" * 64
    hot_path_risk_gate_id: str = "P61_FIXTURE_HOT_PATH_RISK_GATE_ID"
    hot_path_risk_gate_sha256: str = "7" * 64
    fixture_only: bool = True
    real_order_test_requested: bool = False
    real_order_submit_requested: bool = False
    status_polling_requested: bool = False
    cancel_requested: bool = False
    raw_request_persistence_requested: bool = False
    raw_response_persistence_requested: bool = False
    runtime_authority_granted: bool = False

    def canonical_query_parameters(self) -> list[tuple[str, str]]:
        return [
            ("symbol", self.symbol),
            ("side", self.side),
            ("type", self.order_type),
            ("quantity", self.quantity),
            ("newClientOrderId", self.new_client_order_id),
            ("recvWindow", str(self.recv_window_ms)),
            ("timestamp", str(self.timestamp_ms)),
        ]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        canonical_query = urlencode(self.canonical_query_parameters())
        payload["canonical_query_sha256"] = _sha256_json({"canonical_query": canonical_query})
        payload["p61_order_test_request_descriptor_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P61ExternalRuntimeActivation:
    activation_version: str = "p61_external_runtime_activation_v1"
    activation_scope: str = "p61_review_only_disabled"
    adapter_enabled: bool = False
    signer_injection_enabled: bool = False
    transport_injection_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    real_order_test_call_enabled: bool = False
    real_order_submit_endpoint_enabled: bool = False
    one_request_only: bool = True
    testnet_only: bool = True
    order_test_only: bool = True
    separate_operator_approval_validated: bool = False
    external_runtime_process_only: bool = True
    fixture_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p61_external_runtime_activation_sha256"] = _sha256_json(payload)
        return payload


def validate_order_test_adapter_policy(
    policy: Mapping[str, Any] | P61OrderTestAdapterPolicy | None,
) -> dict[str, Any]:
    payload = policy.to_dict() if isinstance(policy, P61OrderTestAdapterPolicy) else dict(policy or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p61_order_test_adapter_policy_sha256"):
        blockers.append("P61_POLICY_EMBEDDED_SHA256_INVALID")
    expected = {
        "package_scope": "separate_external_runtime_package_only",
        "environment": ALLOWED_ENVIRONMENT,
        "venue": ALLOWED_VENUE,
        "base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "method": "POST",
        "path": ALLOWED_ENDPOINTS["test_submit"],
        "symbol": ALLOWED_SYMBOL,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            blockers.append(f"P61_POLICY_{key.upper()}_INVALID")
    for key in (
        "separate_operator_approval_required",
        "external_process_memory_credential_binding_required",
        "redacted_response_required",
        "no_secret_log_scan_required",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P61_POLICY_{key.upper()}_NOT_TRUE")
    for key in (
        "adapter_enabled",
        "network_calls_enabled",
        "signing_enabled",
        "real_order_test_call_enabled",
        "real_order_submit_endpoint_enabled",
        "status_endpoint_enabled",
        "cancel_endpoint_enabled",
        "mainnet_allowed",
        "arbitrary_endpoint_allowed",
        "raw_request_persistence_allowed",
        "raw_response_persistence_allowed",
        "credential_persistence_allowed",
        "credential_logging_allowed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P61_POLICY_{key.upper()}_NOT_FALSE")
    if int(payload.get("max_request_count") or 0) != 1:
        blockers.append("P61_POLICY_MAX_REQUEST_COUNT_NOT_ONE")
    if int(payload.get("max_recv_window_ms") or 0) > 5000:
        blockers.append("P61_POLICY_RECV_WINDOW_TOO_LARGE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "order_test_adapter_policy_valid": not blockers,
        "order_test_adapter_policy_block_reasons": sorted(dict.fromkeys(blockers)),
        "adapter_enabled": payload.get("adapter_enabled") is True,
        "real_order_test_call_enabled": payload.get("real_order_test_call_enabled") is True,
    }
    result["p61_order_test_adapter_policy_validation_sha256"] = _sha256_json(result)
    return result


def validate_external_executor_metadata(
    metadata: Mapping[str, Any] | P61ExternalExecutorMetadata | None,
) -> dict[str, Any]:
    payload = metadata.to_dict() if isinstance(metadata, P61ExternalExecutorMetadata) else dict(metadata or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p61_external_executor_metadata_sha256"):
        blockers.append("P61_EXECUTOR_METADATA_EMBEDDED_SHA256_INVALID")
    expected = {
        "base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "method": "POST",
        "path": ALLOWED_ENDPOINTS["test_submit"],
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            blockers.append(f"P61_EXECUTOR_{key.upper()}_INVALID")
    for key in (
        "external_runtime_only",
        "concrete_external_component",
        "testnet_only",
        "process_memory_credential_binding",
        "credential_reference_id_required",
        "key_fingerprint_sha256_required",
        "redacted_response_only",
        "network_send_capable",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P61_EXECUTOR_{key.upper()}_NOT_TRUE")
    for key in (
        "credential_persistence_allowed",
        "credential_logging_allowed",
        "raw_credential_exposed_to_adapter",
        "included_in_review_package",
        "included_in_default_runtime_candidate",
        "call_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P61_EXECUTOR_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "external_executor_metadata_valid": not blockers,
        "external_executor_metadata_block_reasons": sorted(dict.fromkeys(blockers)),
        "network_send_capable": payload.get("network_send_capable") is True,
        "included_in_review_package": payload.get("included_in_review_package") is True,
    }
    result["p61_external_executor_metadata_validation_sha256"] = _sha256_json(result)
    return result


def validate_order_test_request_descriptor(
    descriptor: Mapping[str, Any] | P61OrderTestRequestDescriptor | None,
    *,
    allow_fixture: bool = True,
) -> dict[str, Any]:
    payload = descriptor.to_dict() if isinstance(descriptor, P61OrderTestRequestDescriptor) else dict(descriptor or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p61_order_test_request_descriptor_sha256"):
        blockers.append("P61_REQUEST_EMBEDDED_SHA256_INVALID")
    expected = {
        "environment": ALLOWED_ENVIRONMENT,
        "venue": ALLOWED_VENUE,
        "base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "method": "POST",
        "path": ALLOWED_ENDPOINTS["test_submit"],
        "symbol": ALLOWED_SYMBOL,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            blockers.append(f"P61_REQUEST_{key.upper()}_INVALID")
    if str(payload.get("side") or "") not in {"BUY", "SELL"}:
        blockers.append("P61_REQUEST_SIDE_INVALID")
    if str(payload.get("order_type") or "") != "MARKET":
        blockers.append("P61_REQUEST_ORDER_TYPE_NOT_MARKET")
    if not _positive_decimal(payload.get("quantity")):
        blockers.append("P61_REQUEST_QUANTITY_NOT_POSITIVE")
    if not str(payload.get("new_client_order_id") or "").strip():
        blockers.append("P61_REQUEST_CLIENT_ORDER_ID_MISSING")
    if len(str(payload.get("new_client_order_id") or "")) > 36:
        blockers.append("P61_REQUEST_CLIENT_ORDER_ID_TOO_LONG")
    recv_window = int(payload.get("recv_window_ms") or 0)
    if recv_window <= 0 or recv_window > 5000:
        blockers.append("P61_REQUEST_RECV_WINDOW_INVALID")
    if int(payload.get("timestamp_ms") or 0) <= 0:
        blockers.append("P61_REQUEST_TIMESTAMP_INVALID")
    if not _is_sha256_hex(payload.get("idempotency_key")):
        blockers.append("P61_REQUEST_IDEMPOTENCY_KEY_INVALID")
    if not _is_sha256_hex(payload.get("hot_path_risk_gate_sha256")):
        blockers.append("P61_REQUEST_RISK_GATE_SHA256_INVALID")
    if payload.get("fixture_only") is True and not allow_fixture:
        blockers.append("P61_REQUEST_FIXTURE_NOT_ALLOWED_FOR_REAL_PATH")
    for key in (
        "real_order_submit_requested",
        "status_polling_requested",
        "cancel_requested",
        "raw_request_persistence_requested",
        "raw_response_persistence_requested",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P61_REQUEST_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "order_test_request_descriptor_valid": not blockers,
        "order_test_request_descriptor_block_reasons": sorted(dict.fromkeys(blockers)),
        "execution_scope": payload.get("execution_scope"),
        "fixture_only": payload.get("fixture_only") is True,
        "real_order_test_requested": payload.get("real_order_test_requested") is True,
    }
    result["p61_order_test_request_descriptor_validation_sha256"] = _sha256_json(result)
    return result


def validate_operator_order_test_approval(
    approval: Mapping[str, Any] | P61OperatorOrderTestApproval | None,
    *,
    require_granted: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = approval.to_dict() if isinstance(approval, P61OperatorOrderTestApproval) else dict(approval or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p61_operator_order_test_approval_sha256"):
        blockers.append("P61_APPROVAL_EMBEDDED_SHA256_INVALID")
    if payload.get("approval_scope") != "p61_order_test_dry_validation_only":
        blockers.append("P61_APPROVAL_SCOPE_INVALID")
    if require_granted:
        if payload.get("approval_granted") is not True:
            blockers.append("P61_APPROVAL_NOT_GRANTED")
        if payload.get("exact_approval_phrase") != EXACT_ORDER_TEST_APPROVAL_PHRASE:
            blockers.append("P61_APPROVAL_PHRASE_INVALID")
        for key in (
            "operator_confirmation_sha256",
            "source_p60_report_sha256",
            "request_descriptor_sha256",
            "key_fingerprint_sha256",
        ):
            if not _is_sha256_hex(payload.get(key)):
                blockers.append(f"P61_APPROVAL_{key.upper()}_INVALID")
        if not str(payload.get("credential_reference_id") or "").strip():
            blockers.append("P61_APPROVAL_CREDENTIAL_REFERENCE_ID_MISSING")
    else:
        if payload.get("approval_granted") is not False:
            blockers.append("P61_APPROVAL_TEMPLATE_GRANTED_NOT_FALSE")
        if payload.get("exact_approval_phrase") not in ("", "OPERATOR_MUST_ENTER_EXACT_PHRASE"):
            blockers.append("P61_APPROVAL_TEMPLATE_PHRASE_MUST_BE_EMPTY_OR_PLACEHOLDER")
    if payload.get("fixture_only") is True and not allow_fixture:
        blockers.append("P61_APPROVAL_FIXTURE_NOT_ALLOWED_FOR_REAL_PATH")
    for key in (
        "one_request_only",
        "testnet_only",
        "order_test_only",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P61_APPROVAL_{key.upper()}_NOT_TRUE")
    for key in (
        "real_order_submit_allowed",
        "status_polling_allowed",
        "cancel_allowed",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P61_APPROVAL_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "operator_order_test_approval_valid": not blockers,
        "operator_order_test_approval_block_reasons": sorted(dict.fromkeys(blockers)),
        "approval_granted": payload.get("approval_granted") is True,
        "fixture_only": payload.get("fixture_only") is True,
    }
    result["p61_operator_order_test_approval_validation_sha256"] = _sha256_json(result)
    return result


def validate_external_runtime_activation(
    activation: Mapping[str, Any] | P61ExternalRuntimeActivation | None,
    *,
    require_enabled: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = activation.to_dict() if isinstance(activation, P61ExternalRuntimeActivation) else dict(activation or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p61_external_runtime_activation_sha256"):
        blockers.append("P61_ACTIVATION_EMBEDDED_SHA256_INVALID")
    if require_enabled:
        expected_scope = NO_NETWORK_SELF_TEST_SCOPE if allow_fixture else ALLOWED_REAL_ORDER_TEST_SCOPE
        if payload.get("activation_scope") != expected_scope:
            blockers.append("P61_ACTIVATION_SCOPE_INVALID")
        for key in (
            "adapter_enabled",
            "signer_injection_enabled",
            "transport_injection_enabled",
            "network_calls_enabled",
            "signing_enabled",
            "real_order_test_call_enabled",
            "one_request_only",
            "testnet_only",
            "order_test_only",
            "separate_operator_approval_validated",
            "external_runtime_process_only",
        ):
            if payload.get(key) is not True:
                blockers.append(f"P61_ACTIVATION_{key.upper()}_NOT_TRUE")
    else:
        if payload.get("activation_scope") != "p61_review_only_disabled":
            blockers.append("P61_ACTIVATION_DISABLED_SCOPE_INVALID")
        for key in (
            "adapter_enabled",
            "signer_injection_enabled",
            "transport_injection_enabled",
            "network_calls_enabled",
            "signing_enabled",
            "real_order_test_call_enabled",
            "real_order_submit_endpoint_enabled",
            "separate_operator_approval_validated",
            "fixture_only",
        ):
            if payload.get(key) is not False:
                blockers.append(f"P61_ACTIVATION_{key.upper()}_NOT_FALSE")
    if payload.get("real_order_submit_endpoint_enabled") is not False:
        blockers.append("P61_ACTIVATION_REAL_ORDER_SUBMIT_ENDPOINT_ENABLED_NOT_FALSE")
    if payload.get("fixture_only") is True and not allow_fixture:
        blockers.append("P61_ACTIVATION_FIXTURE_NOT_ALLOWED_FOR_REAL_PATH")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "external_runtime_activation_valid": not blockers,
        "external_runtime_activation_block_reasons": sorted(dict.fromkeys(blockers)),
        "activation_scope": payload.get("activation_scope"),
        "real_order_test_call_enabled": payload.get("real_order_test_call_enabled") is True,
        "real_order_submit_endpoint_enabled": payload.get("real_order_submit_endpoint_enabled") is True,
    }
    result["p61_external_runtime_activation_validation_sha256"] = _sha256_json(result)
    return result


def validate_redacted_order_test_result(result: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(result or {})
    blockers: list[str] = []
    if payload.get("environment") != ALLOWED_ENVIRONMENT:
        blockers.append("P61_RESULT_ENVIRONMENT_NOT_TESTNET")
    if payload.get("base_url") != ALLOWED_TESTNET_REST_BASE_URL:
        blockers.append("P61_RESULT_BASE_URL_INVALID")
    if payload.get("method") != "POST" or payload.get("path") != ALLOWED_ENDPOINTS["test_submit"]:
        blockers.append("P61_RESULT_ENDPOINT_INVALID")
    if payload.get("test_endpoint_only") is not True:
        blockers.append("P61_RESULT_TEST_ENDPOINT_ONLY_NOT_TRUE")
    if payload.get("redacted_response_only") is not True:
        blockers.append("P61_RESULT_REDACTED_RESPONSE_ONLY_NOT_TRUE")
    for key in (
        "raw_response_included",
        "raw_request_included",
        "raw_signed_payload_included",
        "credential_value_exposed",
        "order_created",
        "actual_order_submission_performed",
        "real_order_endpoint_called",
        "status_endpoint_called",
        "cancel_endpoint_called",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P61_RESULT_{key.upper()}_NOT_FALSE")
    if not _is_sha256_hex(payload.get("request_descriptor_sha256")):
        blockers.append("P61_RESULT_REQUEST_DESCRIPTOR_SHA256_INVALID")
    if not _is_sha256_hex(payload.get("redacted_response_sha256")):
        blockers.append("P61_RESULT_REDACTED_RESPONSE_SHA256_INVALID")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "redacted_order_test_result_valid": not blockers,
        "redacted_order_test_result_block_reasons": sorted(dict.fromkeys(blockers)),
        "http_request_sent": payload.get("http_request_sent") is True,
        "signature_created_in_external_process": payload.get("signature_created_in_external_process") is True,
        "order_created": payload.get("order_created") is True,
    }
    validation["p61_redacted_order_test_result_validation_sha256"] = _sha256_json(validation)
    return validation


class P61NoNetworkInjectedExecutor:
    executor_id = "P61_NO_NETWORK_INJECTED_EXECUTOR_FIXTURE"
    external_runtime_only = True
    concrete_external_component = False
    testnet_only = True
    base_url = ALLOWED_TESTNET_REST_BASE_URL
    method = "POST"
    path = ALLOWED_ENDPOINTS["test_submit"]
    process_memory_credential_binding = True
    credential_persistence_allowed = False
    credential_logging_allowed = False
    raw_credential_exposed_to_adapter = False
    network_send_capable = False

    def execute_signed_order_test(
        self,
        *,
        request_descriptor: Mapping[str, Any],
        credential_reference_id: str,
    ) -> Mapping[str, Any]:
        del credential_reference_id
        request_sha = str(request_descriptor.get("p61_order_test_request_descriptor_sha256") or "")
        redacted = {
            "status_code": 200,
            "accepted_by_fixture": True,
            "response_shape": "empty_object_equivalent_fixture",
            "request_descriptor_sha256": request_sha,
        }
        result = {
            "artifact_type": "p61_no_network_order_test_result_fixture",
            "environment": ALLOWED_ENVIRONMENT,
            "base_url": ALLOWED_TESTNET_REST_BASE_URL,
            "method": "POST",
            "path": ALLOWED_ENDPOINTS["test_submit"],
            "test_endpoint_only": True,
            "redacted_response_only": True,
            "redacted_response_sha256": _sha256_json(redacted),
            "request_descriptor_sha256": request_sha,
            "fixture_executor_used": True,
            "real_external_executor_used": False,
            "http_request_sent": False,
            "signature_created_in_external_process": False,
            "raw_response_included": False,
            "raw_request_included": False,
            "raw_signed_payload_included": False,
            "credential_value_exposed": False,
            "order_created": False,
            "actual_order_submission_performed": False,
            "real_order_endpoint_called": False,
            "status_endpoint_called": False,
            "cancel_endpoint_called": False,
        }
        result["p61_no_network_order_test_result_fixture_sha256"] = _sha256_json(result)
        return result


class RealTestnetOrderTestDryValidationAdapter:
    adapter_id = "p61_real_testnet_order_test_dry_validation_adapter"
    adapter_version = P61_REAL_ORDER_TEST_DRY_VALIDATION_ADAPTER_VERSION

    def __init__(
        self,
        *,
        policy: P61OrderTestAdapterPolicy | None = None,
        key_binding: MetadataOnlyKeyBinding | None = None,
    ) -> None:
        self.policy = policy or P61OrderTestAdapterPolicy()
        self.key_binding = key_binding or MetadataOnlyKeyBinding(
            key_fingerprint_sha256=_sha256_json({"p61": "metadata-only-key-fingerprint"}),
            api_key_fingerprint_sha256=_sha256_json({"p61": "metadata-only-api-key-fingerprint"}),
        )

    def build_safe_request_descriptor(
        self,
        request: Mapping[str, Any] | P61OrderTestRequestDescriptor | None = None,
    ) -> dict[str, Any]:
        payload = request.to_dict() if isinstance(request, P61OrderTestRequestDescriptor) else dict(
            request or P61OrderTestRequestDescriptor().to_dict()
        )
        request_validation = validate_order_test_request_descriptor(payload, allow_fixture=True)
        key_validation = validate_metadata_only_key_binding(self.key_binding)
        blockers = _collect_blockers(request_validation, key_validation)
        if blockers:
            raise AdapterPackageValidationError(";".join(blockers))
        safe = {
            "artifact_type": "p61_safe_order_test_request_descriptor",
            "execution_scope": payload["execution_scope"],
            "environment": payload["environment"],
            "venue": payload["venue"],
            "base_url": payload["base_url"],
            "method": payload["method"],
            "path": payload["path"],
            "symbol": payload["symbol"],
            "side": payload["side"],
            "order_type": payload["order_type"],
            "quantity": payload["quantity"],
            "new_client_order_id": payload["new_client_order_id"],
            "recv_window_ms": payload["recv_window_ms"],
            "timestamp_ms": payload["timestamp_ms"],
            "idempotency_key": payload["idempotency_key"],
            "hot_path_risk_gate_id": payload["hot_path_risk_gate_id"],
            "hot_path_risk_gate_sha256": payload["hot_path_risk_gate_sha256"],
            "canonical_query_sha256": payload["canonical_query_sha256"],
            "credential_reference_id": self.key_binding.secret_reference_id,
            "key_fingerprint_sha256": self.key_binding.key_fingerprint_sha256,
            "fixture_only": payload["fixture_only"],
            "real_order_test_requested": payload["real_order_test_requested"],
            "raw_query_string_included": False,
            "raw_signed_payload_included": False,
            "credential_value_included": False,
        }
        safe["p61_safe_order_test_request_descriptor_sha256"] = _sha256_json(safe)
        return safe

    def run_no_network_injected_executor_self_test(self) -> dict[str, Any]:
        request = P61OrderTestRequestDescriptor().to_dict()
        request_validation = validate_order_test_request_descriptor(request, allow_fixture=True)
        activation = P61ExternalRuntimeActivation(
            activation_scope=NO_NETWORK_SELF_TEST_SCOPE,
            adapter_enabled=True,
            signer_injection_enabled=True,
            transport_injection_enabled=True,
            network_calls_enabled=True,
            signing_enabled=True,
            real_order_test_call_enabled=True,
            separate_operator_approval_validated=True,
            fixture_only=True,
        ).to_dict()
        activation_validation = validate_external_runtime_activation(
            activation, require_enabled=True, allow_fixture=True
        )
        approval = P61OperatorOrderTestApproval(
            exact_approval_phrase=EXACT_ORDER_TEST_APPROVAL_PHRASE,
            operator_confirmation_sha256="1" * 64,
            source_p60_report_sha256="2" * 64,
            request_descriptor_sha256=request["p61_order_test_request_descriptor_sha256"],
            credential_reference_id=self.key_binding.secret_reference_id,
            key_fingerprint_sha256=self.key_binding.key_fingerprint_sha256,
            approval_granted=True,
            fixture_only=True,
        ).to_dict()
        approval_validation = validate_operator_order_test_approval(
            approval, require_granted=True, allow_fixture=True
        )
        blockers = _collect_blockers(request_validation, activation_validation, approval_validation)
        if blockers:
            raise AdapterPackageValidationError(";".join(blockers))
        result = P61NoNetworkInjectedExecutor().execute_signed_order_test(
            request_descriptor=request,
            credential_reference_id=self.key_binding.secret_reference_id,
        )
        result_validation = validate_redacted_order_test_result(result)
        if not result_validation["redacted_order_test_result_valid"]:
            raise AdapterPackageValidationError(";".join(result_validation["redacted_order_test_result_block_reasons"]))
        report = {
            "artifact_type": "p61_no_network_injected_executor_self_test_report",
            "self_test_passed": True,
            "request_descriptor_sha256": request["p61_order_test_request_descriptor_sha256"],
            "safe_request_descriptor_sha256": self.build_safe_request_descriptor(request)[
                "p61_safe_order_test_request_descriptor_sha256"
            ],
            "activation_validation_sha256": activation_validation[
                "p61_external_runtime_activation_validation_sha256"
            ],
            "approval_validation_sha256": approval_validation[
                "p61_operator_order_test_approval_validation_sha256"
            ],
            "redacted_result_validation_sha256": result_validation[
                "p61_redacted_order_test_result_validation_sha256"
            ],
            "fixture_executor_used": True,
            "real_external_executor_used": False,
            "real_order_test_endpoint_call_enabled": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "order_created": False,
            "actual_order_submission_performed": False,
        }
        report["p61_no_network_injected_executor_self_test_report_sha256"] = _sha256_json(report)
        return report

    def execute_approved_external_runtime_order_test(
        self,
        *,
        request: Mapping[str, Any] | P61OrderTestRequestDescriptor,
        approval: Mapping[str, Any] | P61OperatorOrderTestApproval,
        activation: Mapping[str, Any] | P61ExternalRuntimeActivation,
        executor: P61ExternalSignedOrderTestExecutor,
    ) -> Mapping[str, Any]:
        request_payload = request.to_dict() if isinstance(request, P61OrderTestRequestDescriptor) else dict(request)
        approval_payload = approval.to_dict() if isinstance(approval, P61OperatorOrderTestApproval) else dict(approval)
        activation_payload = activation.to_dict() if isinstance(activation, P61ExternalRuntimeActivation) else dict(activation)
        request_validation = validate_order_test_request_descriptor(request_payload, allow_fixture=False)
        approval_validation = validate_operator_order_test_approval(
            approval_payload, require_granted=True, allow_fixture=False
        )
        activation_validation = validate_external_runtime_activation(
            activation_payload, require_enabled=True, allow_fixture=False
        )
        blockers = _collect_blockers(request_validation, approval_validation, activation_validation)
        if request_payload.get("execution_scope") != ALLOWED_REAL_ORDER_TEST_SCOPE:
            blockers.append("P61_REAL_REQUEST_EXECUTION_SCOPE_INVALID")
        if request_payload.get("real_order_test_requested") is not True:
            blockers.append("P61_REAL_REQUEST_REAL_ORDER_TEST_REQUESTED_NOT_TRUE")
        if approval_payload.get("request_descriptor_sha256") != request_payload.get(
            "p61_order_test_request_descriptor_sha256"
        ):
            blockers.append("P61_APPROVAL_REQUEST_DESCRIPTOR_HASH_MISMATCH")
        if approval_payload.get("credential_reference_id") != self.key_binding.secret_reference_id:
            blockers.append("P61_APPROVAL_CREDENTIAL_REFERENCE_MISMATCH")
        if approval_payload.get("key_fingerprint_sha256") != self.key_binding.key_fingerprint_sha256:
            blockers.append("P61_APPROVAL_KEY_FINGERPRINT_MISMATCH")
        executor_checks = {
            "external_runtime_only": getattr(executor, "external_runtime_only", False),
            "concrete_external_component": getattr(executor, "concrete_external_component", False),
            "testnet_only": getattr(executor, "testnet_only", False),
            "base_url": getattr(executor, "base_url", ""),
            "method": getattr(executor, "method", ""),
            "path": getattr(executor, "path", ""),
            "process_memory_credential_binding": getattr(executor, "process_memory_credential_binding", False),
            "credential_persistence_allowed": getattr(executor, "credential_persistence_allowed", True),
            "credential_logging_allowed": getattr(executor, "credential_logging_allowed", True),
            "raw_credential_exposed_to_adapter": getattr(executor, "raw_credential_exposed_to_adapter", True),
            "network_send_capable": getattr(executor, "network_send_capable", False),
        }
        for key in (
            "external_runtime_only",
            "concrete_external_component",
            "testnet_only",
            "process_memory_credential_binding",
            "network_send_capable",
        ):
            if executor_checks[key] is not True:
                blockers.append(f"P61_REAL_EXECUTOR_{key.upper()}_NOT_TRUE")
        if executor_checks["base_url"] != ALLOWED_TESTNET_REST_BASE_URL:
            blockers.append("P61_REAL_EXECUTOR_BASE_URL_INVALID")
        if executor_checks["method"] != "POST" or executor_checks["path"] != ALLOWED_ENDPOINTS["test_submit"]:
            blockers.append("P61_REAL_EXECUTOR_ENDPOINT_INVALID")
        for key in (
            "credential_persistence_allowed",
            "credential_logging_allowed",
            "raw_credential_exposed_to_adapter",
        ):
            if executor_checks[key] is not False:
                blockers.append(f"P61_REAL_EXECUTOR_{key.upper()}_NOT_FALSE")
        if blockers:
            raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(blockers))))
        result = executor.execute_signed_order_test(
            request_descriptor=request_payload,
            credential_reference_id=self.key_binding.secret_reference_id,
        )
        result_validation = validate_redacted_order_test_result(result)
        result_blockers = list(result_validation["redacted_order_test_result_block_reasons"])
        if result.get("http_request_sent") is not True:
            result_blockers.append("P61_REAL_RESULT_HTTP_REQUEST_SENT_NOT_TRUE")
        if result.get("signature_created_in_external_process") is not True:
            result_blockers.append("P61_REAL_RESULT_EXTERNAL_SIGNATURE_NOT_TRUE")
        if result.get("order_test_endpoint_called") is not True:
            result_blockers.append("P61_REAL_RESULT_ORDER_TEST_ENDPOINT_CALLED_NOT_TRUE")
        if result.get("real_external_executor_used") is not True:
            result_blockers.append("P61_REAL_RESULT_EXTERNAL_EXECUTOR_USED_NOT_TRUE")
        if result.get("fixture_executor_used") is not False:
            result_blockers.append("P61_REAL_RESULT_FIXTURE_EXECUTOR_USED_NOT_FALSE")
        if result_blockers:
            raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(result_blockers))))
        return dict(result)

    def execute_real_order_submit(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        del args, kwargs
        raise AdapterPackageDisabledError(
            "P61_REAL_ORDER_SUBMIT_DISABLED_ORDER_TEST_ENDPOINT_ONLY"
        )


def build_p61_no_network_self_test() -> dict[str, Any]:
    adapter = RealTestnetOrderTestDryValidationAdapter()
    report = adapter.run_no_network_injected_executor_self_test()
    real_path_blocked = False
    submit_path_blocked = False
    try:
        adapter.execute_approved_external_runtime_order_test(
            request=P61OrderTestRequestDescriptor(),
            approval=P61OperatorOrderTestApproval(),
            activation=P61ExternalRuntimeActivation(),
            executor=P61NoNetworkInjectedExecutor(),
        )
    except AdapterPackageValidationError:
        real_path_blocked = True
    try:
        adapter.execute_real_order_submit()
    except AdapterPackageDisabledError:
        submit_path_blocked = True
    result = {
        "artifact_type": "p61_real_order_test_adapter_no_network_self_test_report",
        "self_test_passed": bool(report["self_test_passed"] and real_path_blocked and submit_path_blocked),
        "approved_real_path_blocked_with_default_disabled_inputs": real_path_blocked,
        "real_order_submit_path_blocked": submit_path_blocked,
        **report,
    }
    result["p61_real_order_test_adapter_no_network_self_test_report_sha256"] = _sha256_json(result)
    return result


def build_p61_negative_fixture_results() -> dict[str, Any]:
    fixtures: dict[str, Mapping[str, Any]] = {}
    fixtures["policy_adapter_enabled"] = validate_order_test_adapter_policy(
        replace(P61OrderTestAdapterPolicy(), adapter_enabled=True).to_dict()
    )
    fixtures["policy_network_enabled"] = validate_order_test_adapter_policy(
        replace(P61OrderTestAdapterPolicy(), network_calls_enabled=True).to_dict()
    )
    fixtures["policy_real_submit_enabled"] = validate_order_test_adapter_policy(
        replace(P61OrderTestAdapterPolicy(), real_order_submit_endpoint_enabled=True).to_dict()
    )
    fixtures["executor_mainnet"] = validate_external_executor_metadata(
        replace(P61ExternalExecutorMetadata(), base_url="https://fapi.binance.com").to_dict()
    )
    fixtures["executor_in_review_package"] = validate_external_executor_metadata(
        replace(P61ExternalExecutorMetadata(), included_in_review_package=True).to_dict()
    )
    fixtures["request_real_submit"] = validate_order_test_request_descriptor(
        replace(P61OrderTestRequestDescriptor(), real_order_submit_requested=True).to_dict()
    )
    fixtures["request_wrong_symbol"] = validate_order_test_request_descriptor(
        replace(P61OrderTestRequestDescriptor(), symbol="ETHUSDT").to_dict()
    )
    fixtures["approval_runtime_authority"] = validate_operator_order_test_approval(
        replace(P61OperatorOrderTestApproval(), runtime_authority_granted=True).to_dict(),
        require_granted=False,
        allow_fixture=True,
    )
    fixtures["activation_submit_endpoint_enabled"] = validate_external_runtime_activation(
        replace(P61ExternalRuntimeActivation(), real_order_submit_endpoint_enabled=True).to_dict(),
        require_enabled=False,
        allow_fixture=True,
    )
    fixtures["raw_credential_field"] = validate_order_test_request_descriptor(
        {**P61OrderTestRequestDescriptor().to_dict(), "api_secret_value": "DO_NOT_STORE"}
    )

    def blocked(item: Mapping[str, Any]) -> bool:
        validity = [value for key, value in item.items() if key.endswith("_valid")]
        return bool(validity) and all(value is False for value in validity)

    report = {
        "artifact_type": "p61_real_order_test_adapter_negative_fixture_results",
        "fixture_results": fixtures,
        "fixture_count": len(fixtures),
        "all_negative_fixtures_blocked_fail_closed": all(blocked(item) for item in fixtures.values()),
        "http_request_sent": False,
        "order_test_endpoint_called": False,
        "real_order_endpoint_called": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    report["p61_real_order_test_adapter_negative_fixture_results_sha256"] = _sha256_json(report)
    return report


def build_p61_adapter_package_report() -> dict[str, Any]:
    policy = P61OrderTestAdapterPolicy().to_dict()
    executor_metadata = P61ExternalExecutorMetadata().to_dict()
    approval_template = P61OperatorOrderTestApproval().to_dict()
    request_template = P61OrderTestRequestDescriptor().to_dict()
    activation_template = P61ExternalRuntimeActivation().to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256=_sha256_json({"p61": "metadata-only-key-fingerprint"}),
        api_key_fingerprint_sha256=_sha256_json({"p61": "metadata-only-api-key-fingerprint"}),
    ).to_dict()
    validations = {
        "policy": validate_order_test_adapter_policy(policy),
        "executor_metadata": validate_external_executor_metadata(executor_metadata),
        "approval_template": validate_operator_order_test_approval(
            approval_template, require_granted=False, allow_fixture=True
        ),
        "request_template": validate_order_test_request_descriptor(request_template, allow_fixture=True),
        "activation_template": validate_external_runtime_activation(
            activation_template, require_enabled=False, allow_fixture=True
        ),
        "key_binding": validate_metadata_only_key_binding(key_binding),
    }
    self_test = build_p61_no_network_self_test()
    negatives = build_p61_negative_fixture_results()
    blockers = _collect_blockers(*validations.values())
    if not self_test["self_test_passed"]:
        blockers.append("P61_NO_NETWORK_SELF_TEST_FAILED")
    if not negatives["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("P61_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    status = STATUS_ADAPTER_BLOCKED_FAIL_CLOSED if blockers else STATUS_ADAPTER_VALIDATED_DISABLED
    report = {
        "artifact_type": "p61_real_testnet_order_test_dry_validation_adapter_package_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "package_version": P61_REAL_ORDER_TEST_DRY_VALIDATION_ADAPTER_VERSION,
        "policy": policy,
        "external_executor_metadata": executor_metadata,
        "operator_approval_template": approval_template,
        "order_test_request_template": request_template,
        "external_runtime_activation_template": activation_template,
        "metadata_only_key_binding": key_binding,
        "validations": validations,
        "no_network_self_test": self_test,
        "negative_fixture_results": negatives,
        "real_order_test_adapter_implemented": True,
        "approved_external_runtime_order_test_path_implemented": True,
        "external_executor_protocol_implemented": True,
        "testnet_order_test_endpoint_pinned": True,
        "testnet_order_test_path": ALLOWED_ENDPOINTS["test_submit"],
        "real_order_submit_endpoint_permanently_blocked_by_p61": True,
        "concrete_external_executor_included": False,
        "credential_reader_included": False,
        "adapter_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_enabled": False,
        "real_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
        "runtime_mutation_performed": False,
    }
    report["p61_real_testnet_order_test_dry_validation_adapter_package_report_sha256"] = _sha256_json(report)
    return report


__all__ = [
    "ALLOWED_REAL_ORDER_TEST_SCOPE",
    "EXACT_ORDER_TEST_APPROVAL_PHRASE",
    "NO_NETWORK_SELF_TEST_SCOPE",
    "P61ExternalExecutorMetadata",
    "P61ExternalRuntimeActivation",
    "P61ExternalSignedOrderTestExecutor",
    "P61NoNetworkInjectedExecutor",
    "P61OperatorOrderTestApproval",
    "P61OrderTestAdapterPolicy",
    "P61OrderTestRequestDescriptor",
    "RealTestnetOrderTestDryValidationAdapter",
    "STATUS_ADAPTER_BLOCKED_FAIL_CLOSED",
    "STATUS_ADAPTER_VALIDATED_DISABLED",
    "build_p61_adapter_package_report",
    "build_p61_negative_fixture_results",
    "build_p61_no_network_self_test",
    "validate_external_executor_metadata",
    "validate_external_runtime_activation",
    "validate_operator_order_test_approval",
    "validate_order_test_adapter_policy",
    "validate_order_test_request_descriptor",
    "validate_redacted_order_test_result",
]
