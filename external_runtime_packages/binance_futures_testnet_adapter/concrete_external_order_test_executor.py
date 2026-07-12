from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Protocol, Sequence

from .adapter_package import (
    ALLOWED_ENVIRONMENT,
    ALLOWED_ENDPOINTS,
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
)
from .order_test_dry_validation_adapter import (
    P61OrderTestRequestDescriptor,
    validate_order_test_request_descriptor,
    validate_redacted_order_test_result,
)
from .operator_order_test_execution_kit import (
    P62EvidenceExportPolicy,
    P62OperatorRunRequest,
    export_p62_redacted_evidence_bundle,
    validate_evidence_export_policy,
)

P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_VERSION = (
    "p63_concrete_external_order_test_executor_integration_v1"
)
STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED = (
    "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_EXECUTOR_INTEGRATION_BLOCKED_FAIL_CLOSED = (
    "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_BLOCKED_FAIL_CLOSED"
)

P63_NO_NETWORK_SELF_TEST_SCOPE = "p63_no_network_concrete_executor_integration_self_test"
P63_APPROVED_EXTERNAL_RUNTIME_SCOPE = "p63_approved_external_order_test_executor_once"
EXACT_P63_OPERATOR_EXECUTOR_PHRASE = (
    "AUTHORIZE ONE P63 BINANCE FUTURES TESTNET ORDER TEST EXECUTOR RUN ONLY"
)


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_l = str(key).lower()
            child = f"{prefix}.{key}" if prefix else str(key)
            if not isinstance(value, bool) and any(
                token in key_l
                for token in (
                    "api_key_value",
                    "api_secret_value",
                    "secret_value",
                    "private_key",
                    "passphrase",
                    "raw_secret",
                    "secret_file_contents",
                    "credential_value",
                    "raw_signed_payload",
                    "raw_request_body",
                    "raw_response_body",
                    "unredacted_exchange_response",
                )
            ):
                blockers.append(f"P63_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
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


class P63OpaqueCredentialedOrderTestSender(Protocol):
    """Operator-supplied opaque sender contract.

    The sender owns process-memory credential access, signing, and HTTP transport.
    This package passes only a metadata reference and a validated request descriptor.
    """

    sender_id: str
    external_runtime_only: bool
    concrete_external_component: bool
    fixture_only: bool
    testnet_only: bool
    base_url: str
    method: str
    path: str
    process_memory_credential_binding: bool
    credential_persistence_allowed: bool
    credential_logging_allowed: bool
    raw_credential_exposed_to_executor: bool
    raw_request_exposed_to_executor: bool
    raw_response_exposed_to_executor: bool
    signing_capable: bool
    network_send_capable: bool

    def send_signed_order_test(
        self,
        *,
        request_descriptor: Mapping[str, Any],
        credential_reference_id: str,
    ) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class P63ConcreteExecutorPolicy:
    policy_version: str = "p63_concrete_executor_policy_v1"
    package_scope: str = "separate_operator_external_runtime_package_only"
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    symbol: str = ALLOWED_SYMBOL
    max_call_count: int = 1
    concrete_executor_orchestrator_required: bool = True
    opaque_credentialed_sender_required: bool = True
    metadata_only_credential_reference_required: bool = True
    process_memory_credential_boundary_required: bool = True
    exact_operator_phrase_required: bool = True
    p61_request_hash_binding_required: bool = True
    p62_run_hash_binding_required: bool = True
    one_shot_guard_required: bool = True
    redacted_result_required: bool = True
    no_secret_scan_required: bool = True
    executor_enabled: bool = False
    opaque_sender_injection_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    order_test_call_enabled: bool = False
    real_order_submit_enabled: bool = False
    status_polling_enabled: bool = False
    cancel_enabled: bool = False
    credential_reader_included: bool = False
    secret_file_reader_included: bool = False
    secret_file_writer_included: bool = False
    concrete_network_sender_included: bool = False
    raw_request_persistence_allowed: bool = False
    raw_response_persistence_allowed: bool = False
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    runtime_authority_granted: bool = False
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p63_concrete_executor_policy_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P63ConcreteExecutorPackageManifest:
    manifest_version: str = "p63_concrete_executor_package_manifest_v1"
    package_id: str = "p63_concrete_external_order_test_executor_integration"
    package_scope: str = "separate_operator_external_runtime_package_only"
    external_runtime_only: bool = True
    included_in_source_handoff: bool = True
    included_in_external_operator_package: bool = True
    included_in_default_runtime_candidate: bool = False
    concrete_executor_orchestrator_implemented: bool = True
    opaque_sender_protocol_implemented: bool = True
    no_network_fixture_sender_included: bool = True
    concrete_network_sender_included: bool = False
    credential_reader_included: bool = False
    secret_file_reader_included: bool = False
    secret_file_writer_included: bool = False
    concrete_signer_included: bool = False
    real_order_submit_capability_included: bool = False
    enabled_by_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p63_concrete_executor_package_manifest_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P63OpaqueSenderMetadata:
    metadata_version: str = "p63_opaque_sender_metadata_v1"
    sender_id: str = "OPERATOR_SUPPLIED_OPAQUE_CREDENTIALED_ORDER_TEST_SENDER"
    external_runtime_only: bool = True
    concrete_external_component: bool = True
    fixture_only: bool = False
    testnet_only: bool = True
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    process_memory_credential_binding: bool = True
    credential_reference_id_required: bool = True
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    raw_credential_exposed_to_executor: bool = False
    raw_request_exposed_to_executor: bool = False
    raw_response_exposed_to_executor: bool = False
    redacted_result_only: bool = True
    signing_capable: bool = True
    network_send_capable: bool = True
    included_in_review_package: bool = False
    included_in_default_runtime_candidate: bool = False
    call_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p63_opaque_sender_metadata_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P63ConcreteExecutorActivation:
    activation_version: str = "p63_concrete_executor_activation_v1"
    activation_scope: str = "p63_review_only_disabled"
    exact_operator_phrase: str = ""
    operator_confirmation_sha256: str = "0" * 64
    source_p62_report_sha256: str = "0" * 64
    p62_run_request_sha256: str = "0" * 64
    p61_request_descriptor_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64
    executor_enabled: bool = False
    opaque_sender_injection_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    order_test_call_enabled: bool = False
    evidence_export_enabled: bool = False
    no_secret_scan_enabled: bool = False
    separate_operator_approval_validated: bool = False
    one_shot_guard_validated: bool = False
    fixture_only: bool = False
    one_request_only: bool = True
    testnet_only: bool = True
    order_test_only: bool = True
    real_order_submit_enabled: bool = False
    status_polling_enabled: bool = False
    cancel_enabled: bool = False
    raw_credential_allowed: bool = False
    raw_request_persistence_allowed: bool = False
    raw_response_persistence_allowed: bool = False
    runtime_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p63_concrete_executor_activation_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P63ExecutorIntegrationRequest:
    request_version: str = "p63_executor_integration_request_v1"
    execution_scope: str = "p63_review_only_disabled"
    source_p62_report_sha256: str = "0" * 64
    p62_run_request_sha256: str = "0" * 64
    p61_request_descriptor_sha256: str = "0" * 64
    credential_reference_id: str = "OPERATOR_SUPPLIED_TESTNET_CREDENTIAL_REFERENCE_ID"
    key_fingerprint_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64
    integration_requested: bool = False
    operator_approval_validated: bool = False
    one_shot_guard_validated: bool = False
    fixture_only: bool = False
    testnet_only: bool = True
    order_test_only: bool = True
    one_request_only: bool = True
    real_order_submit_allowed: bool = False
    status_polling_allowed: bool = False
    cancel_allowed: bool = False
    raw_credential_allowed: bool = False
    raw_request_persistence_allowed: bool = False
    raw_response_persistence_allowed: bool = False
    runtime_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p63_executor_integration_request_sha256"] = _sha256_json(payload)
        return payload


def validate_concrete_executor_policy(
    policy: Mapping[str, Any] | P63ConcreteExecutorPolicy | None,
) -> dict[str, Any]:
    payload = policy.to_dict() if isinstance(policy, P63ConcreteExecutorPolicy) else dict(policy or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p63_concrete_executor_policy_sha256"):
        blockers.append("P63_POLICY_EMBEDDED_SHA256_INVALID")
    expected = {
        "package_scope": "separate_operator_external_runtime_package_only",
        "environment": ALLOWED_ENVIRONMENT,
        "venue": ALLOWED_VENUE,
        "base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "method": "POST",
        "path": ALLOWED_ENDPOINTS["test_submit"],
        "symbol": ALLOWED_SYMBOL,
        "max_call_count": 1,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            blockers.append(f"P63_POLICY_{key.upper()}_INVALID")
    for key in (
        "concrete_executor_orchestrator_required",
        "opaque_credentialed_sender_required",
        "metadata_only_credential_reference_required",
        "process_memory_credential_boundary_required",
        "exact_operator_phrase_required",
        "p61_request_hash_binding_required",
        "p62_run_hash_binding_required",
        "one_shot_guard_required",
        "redacted_result_required",
        "no_secret_scan_required",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P63_POLICY_{key.upper()}_NOT_TRUE")
    for key in (
        "executor_enabled",
        "opaque_sender_injection_enabled",
        "network_calls_enabled",
        "signing_enabled",
        "order_test_call_enabled",
        "real_order_submit_enabled",
        "status_polling_enabled",
        "cancel_enabled",
        "credential_reader_included",
        "secret_file_reader_included",
        "secret_file_writer_included",
        "concrete_network_sender_included",
        "raw_request_persistence_allowed",
        "raw_response_persistence_allowed",
        "credential_persistence_allowed",
        "credential_logging_allowed",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P63_POLICY_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "concrete_executor_policy_valid": not blockers,
        "concrete_executor_policy_block_reasons": sorted(dict.fromkeys(blockers)),
        "executor_enabled": payload.get("executor_enabled") is True,
    }
    result["p63_concrete_executor_policy_validation_sha256"] = _sha256_json(result)
    return result


def validate_concrete_executor_manifest(
    manifest: Mapping[str, Any] | P63ConcreteExecutorPackageManifest | None,
) -> dict[str, Any]:
    payload = manifest.to_dict() if isinstance(manifest, P63ConcreteExecutorPackageManifest) else dict(manifest or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p63_concrete_executor_package_manifest_sha256"):
        blockers.append("P63_MANIFEST_EMBEDDED_SHA256_INVALID")
    for key in (
        "external_runtime_only",
        "included_in_source_handoff",
        "included_in_external_operator_package",
        "concrete_executor_orchestrator_implemented",
        "opaque_sender_protocol_implemented",
        "no_network_fixture_sender_included",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P63_MANIFEST_{key.upper()}_NOT_TRUE")
    for key in (
        "included_in_default_runtime_candidate",
        "concrete_network_sender_included",
        "credential_reader_included",
        "secret_file_reader_included",
        "secret_file_writer_included",
        "concrete_signer_included",
        "real_order_submit_capability_included",
        "enabled_by_default",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P63_MANIFEST_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "concrete_executor_manifest_valid": not blockers,
        "concrete_executor_manifest_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    result["p63_concrete_executor_manifest_validation_sha256"] = _sha256_json(result)
    return result


def validate_opaque_sender_metadata(
    metadata: Mapping[str, Any] | P63OpaqueSenderMetadata | None,
    *,
    allow_fixture: bool = False,
) -> dict[str, Any]:
    payload = metadata.to_dict() if isinstance(metadata, P63OpaqueSenderMetadata) else dict(metadata or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p63_opaque_sender_metadata_sha256"):
        blockers.append("P63_SENDER_METADATA_EMBEDDED_SHA256_INVALID")
    expected = {
        "base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "method": "POST",
        "path": ALLOWED_ENDPOINTS["test_submit"],
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            blockers.append(f"P63_SENDER_{key.upper()}_INVALID")
    for key in (
        "external_runtime_only",
        "testnet_only",
        "process_memory_credential_binding",
        "credential_reference_id_required",
        "redacted_result_only",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P63_SENDER_{key.upper()}_NOT_TRUE")
    if payload.get("fixture_only") is True:
        if not allow_fixture:
            blockers.append("P63_SENDER_FIXTURE_NOT_ALLOWED")
        if payload.get("concrete_external_component") is not False:
            blockers.append("P63_FIXTURE_SENDER_CONCRETE_COMPONENT_NOT_FALSE")
        for key in ("signing_capable", "network_send_capable"):
            if payload.get(key) is not False:
                blockers.append(f"P63_FIXTURE_SENDER_{key.upper()}_NOT_FALSE")
    else:
        for key in ("concrete_external_component", "signing_capable", "network_send_capable"):
            if payload.get(key) is not True:
                blockers.append(f"P63_SENDER_{key.upper()}_NOT_TRUE")
    for key in (
        "credential_persistence_allowed",
        "credential_logging_allowed",
        "raw_credential_exposed_to_executor",
        "raw_request_exposed_to_executor",
        "raw_response_exposed_to_executor",
        "included_in_review_package",
        "included_in_default_runtime_candidate",
        "call_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P63_SENDER_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "opaque_sender_metadata_valid": not blockers,
        "opaque_sender_metadata_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": payload.get("fixture_only") is True,
        "network_send_capable": payload.get("network_send_capable") is True,
    }
    result["p63_opaque_sender_metadata_validation_sha256"] = _sha256_json(result)
    return result


def validate_concrete_executor_activation(
    activation: Mapping[str, Any] | P63ConcreteExecutorActivation | None,
    *,
    require_enabled: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = activation.to_dict() if isinstance(activation, P63ConcreteExecutorActivation) else dict(activation or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p63_concrete_executor_activation_sha256"):
        blockers.append("P63_ACTIVATION_EMBEDDED_SHA256_INVALID")
    if require_enabled:
        expected_scope = P63_NO_NETWORK_SELF_TEST_SCOPE if allow_fixture else P63_APPROVED_EXTERNAL_RUNTIME_SCOPE
        if payload.get("activation_scope") != expected_scope:
            blockers.append("P63_ACTIVATION_SCOPE_INVALID")
        if payload.get("exact_operator_phrase") != EXACT_P63_OPERATOR_EXECUTOR_PHRASE:
            blockers.append("P63_ACTIVATION_OPERATOR_PHRASE_INVALID")
        for key in (
            "operator_confirmation_sha256",
            "source_p62_report_sha256",
            "p62_run_request_sha256",
            "p61_request_descriptor_sha256",
            "one_shot_nonce_sha256",
        ):
            if not _is_sha256_hex(payload.get(key)) or payload.get(key) == "0" * 64:
                blockers.append(f"P63_ACTIVATION_{key.upper()}_INVALID")
        for key in (
            "executor_enabled",
            "opaque_sender_injection_enabled",
            "network_calls_enabled",
            "signing_enabled",
            "order_test_call_enabled",
            "evidence_export_enabled",
            "no_secret_scan_enabled",
            "separate_operator_approval_validated",
            "one_shot_guard_validated",
            "one_request_only",
            "testnet_only",
            "order_test_only",
        ):
            if payload.get(key) is not True:
                blockers.append(f"P63_ACTIVATION_{key.upper()}_NOT_TRUE")
    else:
        if payload.get("activation_scope") != "p63_review_only_disabled":
            blockers.append("P63_ACTIVATION_DISABLED_SCOPE_INVALID")
        for key in (
            "executor_enabled",
            "opaque_sender_injection_enabled",
            "network_calls_enabled",
            "signing_enabled",
            "order_test_call_enabled",
            "evidence_export_enabled",
            "no_secret_scan_enabled",
            "separate_operator_approval_validated",
            "one_shot_guard_validated",
            "fixture_only",
        ):
            if payload.get(key) is not False:
                blockers.append(f"P63_ACTIVATION_{key.upper()}_NOT_FALSE")
    if payload.get("fixture_only") is True and not allow_fixture:
        blockers.append("P63_ACTIVATION_FIXTURE_NOT_ALLOWED_FOR_REAL_PATH")
    for key in (
        "real_order_submit_enabled",
        "status_polling_enabled",
        "cancel_enabled",
        "raw_credential_allowed",
        "raw_request_persistence_allowed",
        "raw_response_persistence_allowed",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P63_ACTIVATION_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "concrete_executor_activation_valid": not blockers,
        "concrete_executor_activation_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": payload.get("fixture_only") is True,
        "executor_enabled": payload.get("executor_enabled") is True,
    }
    result["p63_concrete_executor_activation_validation_sha256"] = _sha256_json(result)
    return result


def validate_executor_integration_request(
    request: Mapping[str, Any] | P63ExecutorIntegrationRequest | None,
    *,
    require_requested: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = request.to_dict() if isinstance(request, P63ExecutorIntegrationRequest) else dict(request or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p63_executor_integration_request_sha256"):
        blockers.append("P63_REQUEST_EMBEDDED_SHA256_INVALID")
    if require_requested:
        expected_scope = P63_NO_NETWORK_SELF_TEST_SCOPE if allow_fixture else P63_APPROVED_EXTERNAL_RUNTIME_SCOPE
        if payload.get("execution_scope") != expected_scope:
            blockers.append("P63_REQUEST_SCOPE_INVALID")
        for key in (
            "source_p62_report_sha256",
            "p62_run_request_sha256",
            "p61_request_descriptor_sha256",
            "key_fingerprint_sha256",
            "one_shot_nonce_sha256",
        ):
            if not _is_sha256_hex(payload.get(key)) or payload.get(key) == "0" * 64:
                blockers.append(f"P63_REQUEST_{key.upper()}_INVALID")
        if not str(payload.get("credential_reference_id") or "").strip():
            blockers.append("P63_REQUEST_CREDENTIAL_REFERENCE_ID_MISSING")
        for key in ("integration_requested", "operator_approval_validated", "one_shot_guard_validated"):
            if payload.get(key) is not True:
                blockers.append(f"P63_REQUEST_{key.upper()}_NOT_TRUE")
    else:
        if payload.get("execution_scope") != "p63_review_only_disabled":
            blockers.append("P63_REQUEST_DISABLED_SCOPE_INVALID")
        if payload.get("integration_requested") is not False:
            blockers.append("P63_REQUEST_INTEGRATION_REQUESTED_NOT_FALSE")
    if payload.get("fixture_only") is True and not allow_fixture:
        blockers.append("P63_REQUEST_FIXTURE_NOT_ALLOWED_FOR_REAL_PATH")
    for key in ("testnet_only", "order_test_only", "one_request_only"):
        if payload.get(key) is not True:
            blockers.append(f"P63_REQUEST_{key.upper()}_NOT_TRUE")
    for key in (
        "real_order_submit_allowed",
        "status_polling_allowed",
        "cancel_allowed",
        "raw_credential_allowed",
        "raw_request_persistence_allowed",
        "raw_response_persistence_allowed",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P63_REQUEST_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "executor_integration_request_valid": not blockers,
        "executor_integration_request_block_reasons": sorted(dict.fromkeys(blockers)),
        "integration_requested": payload.get("integration_requested") is True,
        "fixture_only": payload.get("fixture_only") is True,
    }
    result["p63_executor_integration_request_validation_sha256"] = _sha256_json(result)
    return result


class P63NoNetworkOpaqueCredentialedSender:
    sender_id = "P63_NO_NETWORK_OPAQUE_CREDENTIALED_SENDER_FIXTURE"
    external_runtime_only = True
    concrete_external_component = False
    fixture_only = True
    testnet_only = True
    base_url = ALLOWED_TESTNET_REST_BASE_URL
    method = "POST"
    path = ALLOWED_ENDPOINTS["test_submit"]
    process_memory_credential_binding = True
    credential_persistence_allowed = False
    credential_logging_allowed = False
    raw_credential_exposed_to_executor = False
    raw_request_exposed_to_executor = False
    raw_response_exposed_to_executor = False
    signing_capable = False
    network_send_capable = False

    def send_signed_order_test(
        self,
        *,
        request_descriptor: Mapping[str, Any],
        credential_reference_id: str,
    ) -> Mapping[str, Any]:
        del credential_reference_id
        request_sha = str(request_descriptor.get("p61_order_test_request_descriptor_sha256") or "")
        redacted = {
            "status_code": 200,
            "response_shape": "empty_object_equivalent_fixture",
            "accepted_by_fixture": True,
            "request_descriptor_sha256": request_sha,
        }
        result = {
            "artifact_type": "p63_no_network_concrete_executor_result_fixture",
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
            "opaque_sender_used": True,
            "http_request_sent": False,
            "signature_created_in_external_process": False,
            "order_test_endpoint_called": False,
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
        result["p63_no_network_concrete_executor_result_fixture_sha256"] = _sha256_json(result)
        return result


class P63ConcreteExternalOrderTestExecutor:
    """Concrete orchestration implementation with an opaque external sender boundary."""

    executor_id = "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_ORCHESTRATOR"
    external_runtime_only = True
    concrete_external_component = True
    testnet_only = True
    base_url = ALLOWED_TESTNET_REST_BASE_URL
    method = "POST"
    path = ALLOWED_ENDPOINTS["test_submit"]
    process_memory_credential_binding = True
    credential_persistence_allowed = False
    credential_logging_allowed = False
    raw_credential_exposed_to_adapter = False
    network_send_capable = True

    def __init__(
        self,
        *,
        activation: P63ConcreteExecutorActivation | Mapping[str, Any] | None = None,
        sender: P63OpaqueCredentialedOrderTestSender | None = None,
        key_binding: MetadataOnlyKeyBinding | None = None,
    ) -> None:
        self.activation = (
            activation.to_dict()
            if isinstance(activation, P63ConcreteExecutorActivation)
            else dict(activation or P63ConcreteExecutorActivation().to_dict())
        )
        self.sender = sender
        self.key_binding = key_binding or MetadataOnlyKeyBinding(
            key_fingerprint_sha256=_sha256_json({"p63": "metadata-only-key-fingerprint"}),
            api_key_fingerprint_sha256=_sha256_json({"p63": "metadata-only-api-key-fingerprint"}),
        )

    @staticmethod
    def _sender_metadata(sender: P63OpaqueCredentialedOrderTestSender) -> dict[str, Any]:
        payload = {
            "metadata_version": "p63_runtime_sender_metadata_v1",
            "sender_id": getattr(sender, "sender_id", ""),
            "external_runtime_only": getattr(sender, "external_runtime_only", False),
            "concrete_external_component": getattr(sender, "concrete_external_component", False),
            "fixture_only": getattr(sender, "fixture_only", False),
            "testnet_only": getattr(sender, "testnet_only", False),
            "base_url": getattr(sender, "base_url", ""),
            "method": getattr(sender, "method", ""),
            "path": getattr(sender, "path", ""),
            "process_memory_credential_binding": getattr(
                sender, "process_memory_credential_binding", False
            ),
            "credential_reference_id_required": True,
            "credential_persistence_allowed": getattr(
                sender, "credential_persistence_allowed", True
            ),
            "credential_logging_allowed": getattr(sender, "credential_logging_allowed", True),
            "raw_credential_exposed_to_executor": getattr(
                sender, "raw_credential_exposed_to_executor", True
            ),
            "raw_request_exposed_to_executor": getattr(
                sender, "raw_request_exposed_to_executor", True
            ),
            "raw_response_exposed_to_executor": getattr(
                sender, "raw_response_exposed_to_executor", True
            ),
            "redacted_result_only": True,
            "signing_capable": getattr(sender, "signing_capable", False),
            "network_send_capable": getattr(sender, "network_send_capable", False),
            "included_in_review_package": False,
            "included_in_default_runtime_candidate": False,
            "call_performed": False,
        }
        payload["p63_opaque_sender_metadata_sha256"] = _sha256_json(payload)
        return payload

    def execute_signed_order_test(
        self,
        *,
        request_descriptor: Mapping[str, Any],
        credential_reference_id: str,
    ) -> Mapping[str, Any]:
        fixture_only = self.activation.get("fixture_only") is True
        activation_validation = validate_concrete_executor_activation(
            self.activation,
            require_enabled=True,
            allow_fixture=fixture_only,
        )
        request_validation = validate_order_test_request_descriptor(
            request_descriptor,
            allow_fixture=fixture_only,
        )
        blockers = _collect_blockers(activation_validation, request_validation)
        if credential_reference_id != self.key_binding.secret_reference_id:
            blockers.append("P63_EXECUTOR_CREDENTIAL_REFERENCE_MISMATCH")
        if self.sender is None:
            blockers.append("P63_EXECUTOR_OPAQUE_SENDER_MISSING")
        else:
            sender_validation = validate_opaque_sender_metadata(
                self._sender_metadata(self.sender),
                allow_fixture=fixture_only,
            )
            blockers.extend(sender_validation["opaque_sender_metadata_block_reasons"])
            if fixture_only and getattr(self.sender, "fixture_only", False) is not True:
                blockers.append("P63_EXECUTOR_FIXTURE_SENDER_REQUIRED")
            if not fixture_only and getattr(self.sender, "fixture_only", True) is not False:
                blockers.append("P63_EXECUTOR_REAL_SENDER_REQUIRED")
        if self.activation.get("p61_request_descriptor_sha256") != request_descriptor.get(
            "p61_order_test_request_descriptor_sha256"
        ):
            blockers.append("P63_EXECUTOR_REQUEST_DESCRIPTOR_HASH_MISMATCH")
        blockers.extend(_walk_forbidden(request_descriptor))
        if blockers:
            raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(blockers))))
        assert self.sender is not None
        result = self.sender.send_signed_order_test(
            request_descriptor=request_descriptor,
            credential_reference_id=credential_reference_id,
        )
        result_validation = validate_redacted_order_test_result(result)
        result_blockers = list(result_validation["redacted_order_test_result_block_reasons"])
        if fixture_only:
            if result.get("fixture_executor_used") is not True:
                result_blockers.append("P63_FIXTURE_RESULT_FIXTURE_EXECUTOR_USED_NOT_TRUE")
            for key in (
                "http_request_sent",
                "signature_created_in_external_process",
                "order_test_endpoint_called",
                "real_external_executor_used",
            ):
                if result.get(key) is not False:
                    result_blockers.append(f"P63_FIXTURE_RESULT_{key.upper()}_NOT_FALSE")
        else:
            for key in (
                "http_request_sent",
                "signature_created_in_external_process",
                "order_test_endpoint_called",
                "real_external_executor_used",
            ):
                if result.get(key) is not True:
                    result_blockers.append(f"P63_REAL_RESULT_{key.upper()}_NOT_TRUE")
            if result.get("fixture_executor_used") is not False:
                result_blockers.append("P63_REAL_RESULT_FIXTURE_EXECUTOR_USED_NOT_FALSE")
        if result_blockers:
            raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(result_blockers))))
        return dict(result)

    def execute_real_order_submit(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        del args, kwargs
        raise AdapterPackageDisabledError(
            "P63_REAL_ORDER_SUBMIT_DISABLED_ORDER_TEST_EXECUTOR_ONLY"
        )


def build_p63_no_network_integration_self_test() -> dict[str, Any]:
    request = P61OrderTestRequestDescriptor().to_dict()
    p62_run = P62OperatorRunRequest(
        execution_scope="p62_no_network_operator_execution_kit_self_test",
        exact_operator_phrase="AUTHORIZE ONE OPERATOR SIDE BINANCE FUTURES TESTNET ORDER TEST RUN ONLY",
        operator_confirmation_sha256="1" * 64,
        source_p61_report_sha256="2" * 64,
        p61_request_descriptor_sha256=request["p61_order_test_request_descriptor_sha256"],
        p61_operator_approval_sha256="3" * 64,
        one_shot_nonce_sha256="4" * 64,
        key_fingerprint_sha256="5" * 64,
        run_requested=True,
        operator_approval_validated=True,
        p61_approval_validated=True,
        fixture_only=True,
    ).to_dict()
    activation = P63ConcreteExecutorActivation(
        activation_scope=P63_NO_NETWORK_SELF_TEST_SCOPE,
        exact_operator_phrase=EXACT_P63_OPERATOR_EXECUTOR_PHRASE,
        operator_confirmation_sha256="6" * 64,
        source_p62_report_sha256="7" * 64,
        p62_run_request_sha256=p62_run["p62_operator_run_request_sha256"],
        p61_request_descriptor_sha256=request["p61_order_test_request_descriptor_sha256"],
        one_shot_nonce_sha256="8" * 64,
        executor_enabled=True,
        opaque_sender_injection_enabled=True,
        network_calls_enabled=True,
        signing_enabled=True,
        order_test_call_enabled=True,
        evidence_export_enabled=True,
        no_secret_scan_enabled=True,
        separate_operator_approval_validated=True,
        one_shot_guard_validated=True,
        fixture_only=True,
    ).to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256="9" * 64,
        api_key_fingerprint_sha256="a" * 64,
    )
    executor = P63ConcreteExternalOrderTestExecutor(
        activation=activation,
        sender=P63NoNetworkOpaqueCredentialedSender(),
        key_binding=key_binding,
    )
    result = executor.execute_signed_order_test(
        request_descriptor=request,
        credential_reference_id=key_binding.secret_reference_id,
    )
    result_validation = validate_redacted_order_test_result(result)
    export_policy_validation = validate_evidence_export_policy(P62EvidenceExportPolicy().to_dict())
    report = {
        "artifact_type": "p63_no_network_concrete_executor_integration_self_test_report",
        "self_test_passed": bool(
            result_validation["redacted_order_test_result_valid"]
            and export_policy_validation["evidence_export_policy_valid"]
            and result.get("fixture_executor_used") is True
            and result.get("http_request_sent") is False
            and result.get("signature_created_in_external_process") is False
        ),
        "concrete_executor_orchestrator_used": True,
        "opaque_fixture_sender_used": True,
        "concrete_network_sender_used": False,
        "p61_request_descriptor_sha256": request[
            "p61_order_test_request_descriptor_sha256"
        ],
        "p62_run_request_sha256": p62_run["p62_operator_run_request_sha256"],
        "p63_activation_sha256": activation["p63_concrete_executor_activation_sha256"],
        "redacted_result_validation_sha256": result_validation[
            "p61_redacted_order_test_result_validation_sha256"
        ],
        "fixture_executor_used": True,
        "real_external_executor_used": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "order_test_endpoint_call_performed": False,
        "actual_order_submission_performed": False,
    }
    report["p63_no_network_concrete_executor_integration_self_test_report_sha256"] = _sha256_json(report)
    return report


def build_p63_negative_fixture_results() -> dict[str, Any]:
    fixtures: dict[str, Mapping[str, Any]] = {
        "policy_executor_enabled": validate_concrete_executor_policy(
            replace(P63ConcreteExecutorPolicy(), executor_enabled=True).to_dict()
        ),
        "policy_raw_response_persistence": validate_concrete_executor_policy(
            replace(P63ConcreteExecutorPolicy(), raw_response_persistence_allowed=True).to_dict()
        ),
        "manifest_default_runtime_included": validate_concrete_executor_manifest(
            replace(
                P63ConcreteExecutorPackageManifest(),
                included_in_default_runtime_candidate=True,
            ).to_dict()
        ),
        "manifest_network_sender_included": validate_concrete_executor_manifest(
            replace(
                P63ConcreteExecutorPackageManifest(),
                concrete_network_sender_included=True,
            ).to_dict()
        ),
        "sender_mainnet": validate_opaque_sender_metadata(
            replace(P63OpaqueSenderMetadata(), base_url="https://fapi.binance.com").to_dict()
        ),
        "sender_exposes_credential": validate_opaque_sender_metadata(
            replace(P63OpaqueSenderMetadata(), raw_credential_exposed_to_executor=True).to_dict()
        ),
        "activation_runtime_authority": validate_concrete_executor_activation(
            replace(P63ConcreteExecutorActivation(), runtime_authority_granted=True).to_dict(),
            require_enabled=False,
            allow_fixture=True,
        ),
        "activation_real_submit": validate_concrete_executor_activation(
            replace(P63ConcreteExecutorActivation(), real_order_submit_enabled=True).to_dict(),
            require_enabled=False,
            allow_fixture=True,
        ),
        "request_raw_credential": validate_executor_integration_request(
            {
                **P63ExecutorIntegrationRequest().to_dict(),
                "api_secret_value": "forbidden",
            },
            require_requested=False,
            allow_fixture=True,
        ),
        "request_runtime_authority": validate_executor_integration_request(
            replace(P63ExecutorIntegrationRequest(), runtime_authority_granted=True).to_dict(),
            require_requested=False,
            allow_fixture=True,
        ),
    }
    blocked = {
        name: any(
            value is False
            for key, value in result.items()
            if key.endswith("_valid")
        )
        for name, result in fixtures.items()
    }
    report = {
        "artifact_type": "p63_concrete_executor_integration_negative_fixture_results",
        "fixture_count": len(fixtures),
        "fixture_results": fixtures,
        "blocked_by_fixture": blocked,
        "all_negative_fixtures_blocked_fail_closed": all(blocked.values()),
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    report["p63_concrete_executor_integration_negative_fixture_results_sha256"] = _sha256_json(report)
    return report


def build_p63_concrete_executor_package_report() -> dict[str, Any]:
    policy = P63ConcreteExecutorPolicy().to_dict()
    manifest = P63ConcreteExecutorPackageManifest().to_dict()
    sender_metadata = P63OpaqueSenderMetadata().to_dict()
    activation = P63ConcreteExecutorActivation().to_dict()
    request = P63ExecutorIntegrationRequest().to_dict()
    validations = {
        "policy": validate_concrete_executor_policy(policy),
        "manifest": validate_concrete_executor_manifest(manifest),
        "sender_metadata": validate_opaque_sender_metadata(sender_metadata),
        "activation": validate_concrete_executor_activation(
            activation, require_enabled=False, allow_fixture=True
        ),
        "request": validate_executor_integration_request(
            request, require_requested=False, allow_fixture=True
        ),
    }
    blockers = _collect_blockers(*validations.values())
    self_test = build_p63_no_network_integration_self_test()
    negatives = build_p63_negative_fixture_results()
    if not self_test["self_test_passed"]:
        blockers.append("P63_NO_NETWORK_SELF_TEST_FAILED")
    if not negatives["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("P63_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    status = (
        STATUS_EXECUTOR_INTEGRATION_BLOCKED_FAIL_CLOSED
        if blockers
        else STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED
    )
    report = {
        "artifact_type": "p63_concrete_external_order_test_executor_package_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p63_version": P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_VERSION,
        "policy": policy,
        "manifest": manifest,
        "opaque_sender_metadata_template": sender_metadata,
        "activation_template": activation,
        "integration_request_template": request,
        "validations": validations,
        "no_network_self_test": self_test,
        "negative_fixture_results": negatives,
        "concrete_executor_orchestrator_implemented": True,
        "opaque_credentialed_sender_protocol_implemented": True,
        "opaque_fixture_sender_included": True,
        "concrete_network_sender_included": False,
        "credential_reader_included": False,
        "secret_file_reader_included": False,
        "secret_file_writer_included": False,
        "concrete_signer_included": False,
        "executor_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "order_test_call_enabled": False,
        "order_test_call_performed": False,
        "real_order_submit_enabled": False,
        "real_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    report["p63_concrete_external_order_test_executor_package_report_sha256"] = _sha256_json(report)
    return report
