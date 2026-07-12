from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

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

P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_VERSION = "p64_opaque_sender_subprocess_bridge_v1"
STATUS_BRIDGE_VALIDATED_DISABLED = (
    "P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_BRIDGE_BLOCKED_FAIL_CLOSED = (
    "P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_BLOCKED_FAIL_CLOSED"
)

P64_NO_NETWORK_SELF_TEST_SCOPE = "p64_no_network_subprocess_bridge_self_test"
P64_APPROVED_EXTERNAL_RUNTIME_SCOPE = "p64_approved_external_order_test_subprocess_once"
EXACT_P64_OPERATOR_BRIDGE_PHRASE = (
    "AUTHORIZE ONE P64 BINANCE FUTURES TESTNET ORDER TEST SUBPROCESS BRIDGE RUN ONLY"
)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
                    "authorization_header",
                )
            ):
                blockers.append(f"P64_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
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


@dataclass(frozen=True)
class P64SubprocessBridgePolicy:
    policy_version: str = "p64_subprocess_bridge_policy_v1"
    package_scope: str = "separate_operator_external_runtime_package_only"
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    symbol: str = ALLOWED_SYMBOL
    max_call_count: int = 1
    shell_allowed: bool = False
    inherited_environment_allowed: bool = False
    stdin_payload_allowed: bool = False
    request_file_contains_metadata_only: bool = True
    request_file_mode: str = "0600"
    request_file_deleted_after_run: bool = True
    stdout_redacted_json_only: bool = True
    stderr_output_allowed: bool = False
    stdout_max_bytes: int = 65536
    stderr_max_bytes: int = 8192
    timeout_seconds: int = 30
    absolute_program_path_required: bool = True
    program_sha256_required: bool = True
    launcher_sha256_required: bool = True
    fixed_argv_required: bool = True
    process_memory_credential_boundary_required: bool = True
    metadata_only_credential_reference_required: bool = True
    executable_in_review_package_allowed: bool = False
    executable_in_default_runtime_candidate_allowed: bool = False
    bridge_enabled: bool = False
    subprocess_execution_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    order_test_call_enabled: bool = False
    real_order_submit_enabled: bool = False
    status_polling_enabled: bool = False
    cancel_enabled: bool = False
    credential_reader_included: bool = False
    secret_file_reader_included: bool = False
    secret_file_writer_included: bool = False
    raw_request_persistence_allowed: bool = False
    raw_response_persistence_allowed: bool = False
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    runtime_authority_granted: bool = False
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p64_subprocess_bridge_policy_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P64SubprocessBridgePackageManifest:
    manifest_version: str = "p64_subprocess_bridge_package_manifest_v1"
    package_id: str = "p64_opaque_sender_subprocess_bridge"
    package_scope: str = "separate_operator_external_runtime_package_only"
    external_runtime_only: bool = True
    included_in_source_handoff: bool = True
    included_in_external_operator_package: bool = True
    included_in_default_runtime_candidate: bool = False
    subprocess_bridge_implemented: bool = True
    metadata_only_request_file_implemented: bool = True
    executable_hash_attestation_implemented: bool = True
    launcher_hash_attestation_implemented: bool = True
    minimal_environment_implemented: bool = True
    shell_disabled: bool = True
    stdin_disabled: bool = True
    timeout_guard_implemented: bool = True
    output_size_guard_implemented: bool = True
    redacted_json_stdout_contract_implemented: bool = True
    no_network_fixture_sender_program_generated_only_in_self_test: bool = True
    concrete_network_sender_program_included: bool = False
    credential_reader_included: bool = False
    secret_file_reader_included: bool = False
    secret_file_writer_included: bool = False
    real_order_submit_capability_included: bool = False
    enabled_by_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p64_subprocess_bridge_package_manifest_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P64SubprocessSenderMetadata:
    metadata_version: str = "p64_subprocess_sender_metadata_v1"
    sender_id: str = "OPERATOR_INSTALLED_OPAQUE_ORDER_TEST_SENDER_SUBPROCESS"
    external_runtime_only: bool = True
    concrete_external_component: bool = True
    fixture_only: bool = False
    testnet_only: bool = True
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    launcher_path: str = ""
    launcher_sha256: str = "0" * 64
    sender_program_path: str = ""
    sender_program_sha256: str = "0" * 64
    argv_contract: str = "launcher sender_program --request-file ABSOLUTE_JSON_PATH"
    shell_used: bool = False
    inherited_environment_used: bool = False
    stdin_used: bool = False
    process_memory_credential_binding: bool = True
    credential_reference_id_required: bool = True
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    raw_credential_exposed_to_bridge: bool = False
    raw_request_exposed_to_bridge: bool = False
    raw_response_exposed_to_bridge: bool = False
    redacted_json_stdout_only: bool = True
    stderr_output_allowed: bool = False
    signing_capable: bool = True
    network_send_capable: bool = True
    included_in_review_package: bool = False
    included_in_default_runtime_candidate: bool = False
    call_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p64_subprocess_sender_metadata_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P64SubprocessBridgeActivation:
    activation_version: str = "p64_subprocess_bridge_activation_v1"
    activation_scope: str = "p64_review_only_disabled"
    exact_operator_phrase: str = ""
    operator_confirmation_sha256: str = "0" * 64
    source_p63_report_sha256: str = "0" * 64
    p63_integration_request_sha256: str = "0" * 64
    p61_request_descriptor_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64
    bridge_enabled: bool = False
    subprocess_execution_enabled: bool = False
    sender_program_injection_enabled: bool = False
    evidence_capture_enabled: bool = False
    no_secret_scan_enabled: bool = False
    executable_hashes_validated: bool = False
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
        payload["p64_subprocess_bridge_activation_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P64SubprocessBridgeRequest:
    request_version: str = "p64_subprocess_bridge_request_v1"
    execution_scope: str = "p64_review_only_no_subprocess"
    bridge_requested: bool = False
    fixture_only: bool = False
    credential_reference_id: str = "TESTNET_KEY_REFERENCE_METADATA_ONLY"
    key_fingerprint_sha256: str = "0" * 64
    source_p63_report_sha256: str = "0" * 64
    p63_integration_request_sha256: str = "0" * 64
    p61_request_descriptor_sha256: str = "0" * 64
    sender_metadata_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64
    testnet_only: bool = True
    order_test_only: bool = True
    one_request_only: bool = True
    real_order_submit_requested: bool = False
    status_polling_requested: bool = False
    cancel_requested: bool = False
    raw_credential_included: bool = False
    raw_request_included: bool = False
    runtime_authority_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p64_subprocess_bridge_request_sha256"] = _sha256_json(payload)
        return payload


def validate_subprocess_bridge_policy(
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(policy or {})
    blockers: list[str] = []
    if payload.get("environment") != ALLOWED_ENVIRONMENT:
        blockers.append("P64_POLICY_ENVIRONMENT_INVALID")
    if payload.get("venue") != ALLOWED_VENUE:
        blockers.append("P64_POLICY_VENUE_INVALID")
    if payload.get("base_url") != ALLOWED_TESTNET_REST_BASE_URL:
        blockers.append("P64_POLICY_BASE_URL_INVALID")
    if payload.get("method") != "POST" or payload.get("path") != ALLOWED_ENDPOINTS["test_submit"]:
        blockers.append("P64_POLICY_ENDPOINT_INVALID")
    if payload.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P64_POLICY_SYMBOL_INVALID")
    if payload.get("max_call_count") != 1:
        blockers.append("P64_POLICY_MAX_CALL_COUNT_NOT_ONE")
    for key in (
        "request_file_contains_metadata_only",
        "request_file_deleted_after_run",
        "stdout_redacted_json_only",
        "absolute_program_path_required",
        "program_sha256_required",
        "launcher_sha256_required",
        "fixed_argv_required",
        "process_memory_credential_boundary_required",
        "metadata_only_credential_reference_required",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P64_POLICY_{key.upper()}_NOT_TRUE")
    for key in (
        "shell_allowed",
        "inherited_environment_allowed",
        "stdin_payload_allowed",
        "stderr_output_allowed",
        "executable_in_review_package_allowed",
        "executable_in_default_runtime_candidate_allowed",
        "bridge_enabled",
        "subprocess_execution_enabled",
        "network_calls_enabled",
        "signing_enabled",
        "order_test_call_enabled",
        "real_order_submit_enabled",
        "status_polling_enabled",
        "cancel_enabled",
        "credential_reader_included",
        "secret_file_reader_included",
        "secret_file_writer_included",
        "raw_request_persistence_allowed",
        "raw_response_persistence_allowed",
        "credential_persistence_allowed",
        "credential_logging_allowed",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P64_POLICY_{key.upper()}_NOT_FALSE")
    if payload.get("request_file_mode") != "0600":
        blockers.append("P64_POLICY_REQUEST_FILE_MODE_INVALID")
    if not isinstance(payload.get("timeout_seconds"), int) or not 1 <= payload["timeout_seconds"] <= 60:
        blockers.append("P64_POLICY_TIMEOUT_INVALID")
    if not isinstance(payload.get("stdout_max_bytes"), int) or not 1024 <= payload["stdout_max_bytes"] <= 262144:
        blockers.append("P64_POLICY_STDOUT_LIMIT_INVALID")
    if not isinstance(payload.get("stderr_max_bytes"), int) or not 0 <= payload["stderr_max_bytes"] <= 32768:
        blockers.append("P64_POLICY_STDERR_LIMIT_INVALID")
    if not _verify_embedded_hash(payload, "p64_subprocess_bridge_policy_sha256"):
        blockers.append("P64_POLICY_HASH_MISMATCH")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "subprocess_bridge_policy_valid": not blockers,
        "subprocess_bridge_policy_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    validation["p64_subprocess_bridge_policy_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_subprocess_bridge_manifest(
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(manifest or {})
    blockers: list[str] = []
    for key in (
        "external_runtime_only",
        "included_in_source_handoff",
        "included_in_external_operator_package",
        "subprocess_bridge_implemented",
        "metadata_only_request_file_implemented",
        "executable_hash_attestation_implemented",
        "launcher_hash_attestation_implemented",
        "minimal_environment_implemented",
        "shell_disabled",
        "stdin_disabled",
        "timeout_guard_implemented",
        "output_size_guard_implemented",
        "redacted_json_stdout_contract_implemented",
        "no_network_fixture_sender_program_generated_only_in_self_test",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P64_MANIFEST_{key.upper()}_NOT_TRUE")
    for key in (
        "included_in_default_runtime_candidate",
        "concrete_network_sender_program_included",
        "credential_reader_included",
        "secret_file_reader_included",
        "secret_file_writer_included",
        "real_order_submit_capability_included",
        "enabled_by_default",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P64_MANIFEST_{key.upper()}_NOT_FALSE")
    if not _verify_embedded_hash(payload, "p64_subprocess_bridge_package_manifest_sha256"):
        blockers.append("P64_MANIFEST_HASH_MISMATCH")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "subprocess_bridge_manifest_valid": not blockers,
        "subprocess_bridge_manifest_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    validation["p64_subprocess_bridge_manifest_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_subprocess_sender_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    allow_fixture: bool,
    require_paths: bool,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    blockers: list[str] = []
    fixture_only = payload.get("fixture_only") is True
    if fixture_only and not allow_fixture:
        blockers.append("P64_SENDER_FIXTURE_NOT_ALLOWED")
    for key in ("external_runtime_only", "testnet_only", "process_memory_credential_binding", "credential_reference_id_required", "redacted_json_stdout_only"):
        if payload.get(key) is not True:
            blockers.append(f"P64_SENDER_{key.upper()}_NOT_TRUE")
    if not fixture_only and payload.get("concrete_external_component") is not True:
        blockers.append("P64_SENDER_CONCRETE_EXTERNAL_COMPONENT_NOT_TRUE")
    if fixture_only and payload.get("concrete_external_component") is not False:
        blockers.append("P64_FIXTURE_SENDER_CONCRETE_EXTERNAL_COMPONENT_NOT_FALSE")
    if payload.get("base_url") != ALLOWED_TESTNET_REST_BASE_URL:
        blockers.append("P64_SENDER_BASE_URL_INVALID")
    if payload.get("method") != "POST" or payload.get("path") != ALLOWED_ENDPOINTS["test_submit"]:
        blockers.append("P64_SENDER_ENDPOINT_INVALID")
    for key in (
        "shell_used",
        "inherited_environment_used",
        "stdin_used",
        "credential_persistence_allowed",
        "credential_logging_allowed",
        "raw_credential_exposed_to_bridge",
        "raw_request_exposed_to_bridge",
        "raw_response_exposed_to_bridge",
        "stderr_output_allowed",
        "included_in_review_package",
        "included_in_default_runtime_candidate",
        "call_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P64_SENDER_{key.upper()}_NOT_FALSE")
    if fixture_only:
        for key in ("signing_capable", "network_send_capable"):
            if payload.get(key) is not False:
                blockers.append(f"P64_FIXTURE_SENDER_{key.upper()}_NOT_FALSE")
    else:
        for key in ("signing_capable", "network_send_capable"):
            if payload.get(key) is not True:
                blockers.append(f"P64_REAL_SENDER_{key.upper()}_NOT_TRUE")
    if require_paths:
        for field in ("launcher_path", "sender_program_path"):
            value = payload.get(field)
            if not isinstance(value, str) or not value or not Path(value).is_absolute():
                blockers.append(f"P64_SENDER_{field.upper()}_NOT_ABSOLUTE")
            elif not Path(value).is_file():
                blockers.append(f"P64_SENDER_{field.upper()}_NOT_FILE")
        for field in ("launcher_sha256", "sender_program_sha256"):
            if not _is_sha256_hex(payload.get(field)):
                blockers.append(f"P64_SENDER_{field.upper()}_INVALID")
        if not blockers:
            if _sha256_file(payload["launcher_path"]) != payload["launcher_sha256"]:
                blockers.append("P64_SENDER_LAUNCHER_SHA256_MISMATCH")
            if _sha256_file(payload["sender_program_path"]) != payload["sender_program_sha256"]:
                blockers.append("P64_SENDER_PROGRAM_SHA256_MISMATCH")
    if not _verify_embedded_hash(payload, "p64_subprocess_sender_metadata_sha256"):
        blockers.append("P64_SENDER_METADATA_HASH_MISMATCH")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "subprocess_sender_metadata_valid": not blockers,
        "subprocess_sender_metadata_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": fixture_only,
    }
    validation["p64_subprocess_sender_metadata_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_subprocess_bridge_activation(
    activation: Mapping[str, Any] | None,
    *,
    require_enabled: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = dict(activation or {})
    blockers: list[str] = []
    fixture_only = payload.get("fixture_only") is True
    expected_scope = P64_NO_NETWORK_SELF_TEST_SCOPE if fixture_only else P64_APPROVED_EXTERNAL_RUNTIME_SCOPE
    if fixture_only and not allow_fixture:
        blockers.append("P64_ACTIVATION_FIXTURE_NOT_ALLOWED")
    if require_enabled:
        if payload.get("activation_scope") != expected_scope:
            blockers.append("P64_ACTIVATION_SCOPE_INVALID")
        if payload.get("exact_operator_phrase") != EXACT_P64_OPERATOR_BRIDGE_PHRASE:
            blockers.append("P64_ACTIVATION_OPERATOR_PHRASE_INVALID")
        for key in (
            "bridge_enabled",
            "subprocess_execution_enabled",
            "sender_program_injection_enabled",
            "evidence_capture_enabled",
            "no_secret_scan_enabled",
            "executable_hashes_validated",
            "separate_operator_approval_validated",
            "one_shot_guard_validated",
            "one_request_only",
            "testnet_only",
            "order_test_only",
        ):
            if payload.get(key) is not True:
                blockers.append(f"P64_ACTIVATION_{key.upper()}_NOT_TRUE")
        for key in (
            "operator_confirmation_sha256",
            "source_p63_report_sha256",
            "p63_integration_request_sha256",
            "p61_request_descriptor_sha256",
            "one_shot_nonce_sha256",
        ):
            if not _is_sha256_hex(payload.get(key)) or payload.get(key) == "0" * 64:
                blockers.append(f"P64_ACTIVATION_{key.upper()}_INVALID")
    else:
        for key in (
            "bridge_enabled",
            "subprocess_execution_enabled",
            "sender_program_injection_enabled",
            "evidence_capture_enabled",
            "no_secret_scan_enabled",
            "executable_hashes_validated",
            "separate_operator_approval_validated",
            "one_shot_guard_validated",
        ):
            if payload.get(key) is not False:
                blockers.append(f"P64_ACTIVATION_TEMPLATE_{key.upper()}_NOT_FALSE")
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
            blockers.append(f"P64_ACTIVATION_{key.upper()}_NOT_FALSE")
    if not _verify_embedded_hash(payload, "p64_subprocess_bridge_activation_sha256"):
        blockers.append("P64_ACTIVATION_HASH_MISMATCH")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "subprocess_bridge_activation_valid": not blockers,
        "subprocess_bridge_activation_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": fixture_only,
    }
    validation["p64_subprocess_bridge_activation_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_subprocess_bridge_request(
    request: Mapping[str, Any] | None,
    *,
    require_requested: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = dict(request or {})
    blockers: list[str] = []
    fixture_only = payload.get("fixture_only") is True
    expected_scope = P64_NO_NETWORK_SELF_TEST_SCOPE if fixture_only else P64_APPROVED_EXTERNAL_RUNTIME_SCOPE
    if fixture_only and not allow_fixture:
        blockers.append("P64_REQUEST_FIXTURE_NOT_ALLOWED")
    if require_requested:
        if payload.get("execution_scope") != expected_scope:
            blockers.append("P64_REQUEST_SCOPE_INVALID")
        if payload.get("bridge_requested") is not True:
            blockers.append("P64_REQUEST_BRIDGE_REQUESTED_NOT_TRUE")
        for key in (
            "key_fingerprint_sha256",
            "source_p63_report_sha256",
            "p63_integration_request_sha256",
            "p61_request_descriptor_sha256",
            "sender_metadata_sha256",
            "one_shot_nonce_sha256",
        ):
            if not _is_sha256_hex(payload.get(key)) or payload.get(key) == "0" * 64:
                blockers.append(f"P64_REQUEST_{key.upper()}_INVALID")
    else:
        if payload.get("bridge_requested") is not False:
            blockers.append("P64_REQUEST_TEMPLATE_BRIDGE_REQUESTED_NOT_FALSE")
    if not isinstance(payload.get("credential_reference_id"), str) or not payload.get("credential_reference_id"):
        blockers.append("P64_REQUEST_CREDENTIAL_REFERENCE_ID_MISSING")
    for key in ("testnet_only", "order_test_only", "one_request_only"):
        if payload.get(key) is not True:
            blockers.append(f"P64_REQUEST_{key.upper()}_NOT_TRUE")
    for key in (
        "real_order_submit_requested",
        "status_polling_requested",
        "cancel_requested",
        "raw_credential_included",
        "raw_request_included",
        "runtime_authority_requested",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P64_REQUEST_{key.upper()}_NOT_FALSE")
    if not _verify_embedded_hash(payload, "p64_subprocess_bridge_request_sha256"):
        blockers.append("P64_REQUEST_HASH_MISMATCH")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "subprocess_bridge_request_valid": not blockers,
        "subprocess_bridge_request_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": fixture_only,
    }
    validation["p64_subprocess_bridge_request_validation_sha256"] = _sha256_json(validation)
    return validation


class P64OpaqueSenderSubprocessBridge:
    """Launches an operator-installed sender program through a fail-closed subprocess boundary."""

    sender_id = "P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE"
    external_runtime_only = True
    concrete_external_component = True
    fixture_only = False
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
    signing_capable = True
    network_send_capable = True

    def __init__(
        self,
        *,
        policy: Mapping[str, Any] | P64SubprocessBridgePolicy | None = None,
        activation: Mapping[str, Any] | P64SubprocessBridgeActivation | None = None,
        sender_metadata: Mapping[str, Any] | P64SubprocessSenderMetadata | None = None,
        bridge_request: Mapping[str, Any] | P64SubprocessBridgeRequest | None = None,
        key_binding: MetadataOnlyKeyBinding | None = None,
    ) -> None:
        self.policy = policy.to_dict() if isinstance(policy, P64SubprocessBridgePolicy) else dict(policy or P64SubprocessBridgePolicy().to_dict())
        self.activation = activation.to_dict() if isinstance(activation, P64SubprocessBridgeActivation) else dict(activation or P64SubprocessBridgeActivation().to_dict())
        self.sender_metadata = sender_metadata.to_dict() if isinstance(sender_metadata, P64SubprocessSenderMetadata) else dict(sender_metadata or P64SubprocessSenderMetadata().to_dict())
        self.bridge_request = bridge_request.to_dict() if isinstance(bridge_request, P64SubprocessBridgeRequest) else dict(bridge_request or P64SubprocessBridgeRequest().to_dict())
        self.key_binding = key_binding or MetadataOnlyKeyBinding(
            key_fingerprint_sha256=_sha256_json({"p64": "metadata-only-key-fingerprint"}),
            api_key_fingerprint_sha256=_sha256_json({"p64": "metadata-only-api-key-fingerprint"}),
        )

    def _validate_runtime(self, request_descriptor: Mapping[str, Any]) -> bool:
        fixture_only = self.activation.get("fixture_only") is True
        validations = (
            validate_subprocess_bridge_policy(self.policy),
            validate_subprocess_sender_metadata(self.sender_metadata, allow_fixture=fixture_only, require_paths=True),
            validate_subprocess_bridge_activation(self.activation, require_enabled=True, allow_fixture=fixture_only),
            validate_subprocess_bridge_request(self.bridge_request, require_requested=True, allow_fixture=fixture_only),
            validate_order_test_request_descriptor(request_descriptor, allow_fixture=fixture_only),
        )
        blockers = _collect_blockers(*validations)
        if self.activation.get("p61_request_descriptor_sha256") != request_descriptor.get("p61_order_test_request_descriptor_sha256"):
            blockers.append("P64_BRIDGE_ACTIVATION_REQUEST_DESCRIPTOR_HASH_MISMATCH")
        if self.bridge_request.get("p61_request_descriptor_sha256") != request_descriptor.get("p61_order_test_request_descriptor_sha256"):
            blockers.append("P64_BRIDGE_REQUEST_DESCRIPTOR_HASH_MISMATCH")
        if self.bridge_request.get("sender_metadata_sha256") != self.sender_metadata.get("p64_subprocess_sender_metadata_sha256"):
            blockers.append("P64_BRIDGE_SENDER_METADATA_HASH_MISMATCH")
        if self.bridge_request.get("credential_reference_id") != self.key_binding.secret_reference_id:
            blockers.append("P64_BRIDGE_CREDENTIAL_REFERENCE_MISMATCH")
        if self.bridge_request.get("key_fingerprint_sha256") != self.key_binding.key_fingerprint_sha256:
            blockers.append("P64_BRIDGE_KEY_FINGERPRINT_MISMATCH")
        if self.activation.get("source_p63_report_sha256") != self.bridge_request.get("source_p63_report_sha256"):
            blockers.append("P64_BRIDGE_SOURCE_P63_HASH_MISMATCH")
        if self.activation.get("p63_integration_request_sha256") != self.bridge_request.get("p63_integration_request_sha256"):
            blockers.append("P64_BRIDGE_P63_REQUEST_HASH_MISMATCH")
        if self.activation.get("one_shot_nonce_sha256") != self.bridge_request.get("one_shot_nonce_sha256"):
            blockers.append("P64_BRIDGE_NONCE_HASH_MISMATCH")
        blockers.extend(_walk_forbidden(request_descriptor))
        if blockers:
            raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(blockers))))
        return fixture_only

    def send_signed_order_test(
        self,
        *,
        request_descriptor: Mapping[str, Any],
        credential_reference_id: str,
    ) -> Mapping[str, Any]:
        if credential_reference_id != self.key_binding.secret_reference_id:
            raise AdapterPackageValidationError("P64_BRIDGE_RUNTIME_CREDENTIAL_REFERENCE_MISMATCH")
        fixture_only = self._validate_runtime(request_descriptor)
        if not fixture_only and self.activation.get("activation_scope") != P64_APPROVED_EXTERNAL_RUNTIME_SCOPE:
            raise AdapterPackageDisabledError("P64_REAL_SUBPROCESS_SCOPE_NOT_APPROVED")

        safe_input = {
            "artifact_type": "p64_metadata_only_subprocess_input",
            "execution_scope": self.activation["activation_scope"],
            "credential_reference_id": credential_reference_id,
            "key_fingerprint_sha256": self.key_binding.key_fingerprint_sha256,
            "request_descriptor": dict(request_descriptor),
            "source_p63_report_sha256": self.bridge_request["source_p63_report_sha256"],
            "p63_integration_request_sha256": self.bridge_request["p63_integration_request_sha256"],
            "one_shot_nonce_sha256": self.bridge_request["one_shot_nonce_sha256"],
            "raw_credential_included": False,
            "raw_request_included": False,
        }
        forbidden = _walk_forbidden(safe_input)
        if forbidden:
            raise AdapterPackageValidationError(";".join(forbidden))
        safe_input["p64_metadata_only_subprocess_input_sha256"] = _sha256_json(safe_input)

        timeout_seconds = int(self.policy["timeout_seconds"])
        stdout_limit = int(self.policy["stdout_max_bytes"])
        stderr_limit = int(self.policy["stderr_max_bytes"])
        with tempfile.TemporaryDirectory(prefix="p64_subprocess_bridge_") as tmp:
            tmp_path = Path(tmp)
            request_file = tmp_path / "metadata_request.json"
            request_file.write_text(
                json.dumps(safe_input, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            os.chmod(request_file, 0o600)
            command = [
                str(self.sender_metadata["launcher_path"]),
                str(self.sender_metadata["sender_program_path"]),
                "--request-file",
                str(request_file),
            ]
            minimal_env = {
                "PYTHONIOENCODING": "utf-8",
                "P64_EXECUTION_SCOPE": str(self.activation["activation_scope"]),
                "P64_CREDENTIAL_REFERENCE_ID": credential_reference_id,
                "P64_REQUEST_FILE": str(request_file),
            }
            try:
                completed = subprocess.run(
                    command,
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=tmp_path,
                    env=minimal_env,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise AdapterPackageValidationError("P64_SUBPROCESS_TIMEOUT") from exc
            stdout = bytes(completed.stdout or b"")
            stderr = bytes(completed.stderr or b"")
            if len(stdout) > stdout_limit:
                raise AdapterPackageValidationError("P64_SUBPROCESS_STDOUT_LIMIT_EXCEEDED")
            if len(stderr) > stderr_limit:
                raise AdapterPackageValidationError("P64_SUBPROCESS_STDERR_LIMIT_EXCEEDED")
            if completed.returncode != 0:
                raise AdapterPackageValidationError("P64_SUBPROCESS_NONZERO_EXIT")
            if stderr:
                raise AdapterPackageValidationError("P64_SUBPROCESS_STDERR_NOT_EMPTY")
            try:
                decoded = stdout.decode("utf-8")
                result = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AdapterPackageValidationError("P64_SUBPROCESS_STDOUT_NOT_SINGLE_JSON_OBJECT") from exc
            if not isinstance(result, dict):
                raise AdapterPackageValidationError("P64_SUBPROCESS_RESULT_NOT_OBJECT")
            result_validation = validate_redacted_order_test_result(result)
            result_blockers = list(result_validation["redacted_order_test_result_block_reasons"])
            result_blockers.extend(_walk_forbidden(result))
            if fixture_only:
                for key in (
                    "http_request_sent",
                    "signature_created_in_external_process",
                    "order_test_endpoint_called",
                    "real_external_executor_used",
                ):
                    if result.get(key) is not False:
                        result_blockers.append(f"P64_FIXTURE_RESULT_{key.upper()}_NOT_FALSE")
                if result.get("fixture_executor_used") is not True:
                    result_blockers.append("P64_FIXTURE_RESULT_FIXTURE_EXECUTOR_USED_NOT_TRUE")
            else:
                for key in (
                    "http_request_sent",
                    "signature_created_in_external_process",
                    "order_test_endpoint_called",
                    "real_external_executor_used",
                ):
                    if result.get(key) is not True:
                        result_blockers.append(f"P64_REAL_RESULT_{key.upper()}_NOT_TRUE")
                if result.get("fixture_executor_used") is not False:
                    result_blockers.append("P64_REAL_RESULT_FIXTURE_EXECUTOR_USED_NOT_FALSE")
            if result_blockers:
                raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(result_blockers))))
            result = dict(result)
            result.update(
                {
                    "p64_subprocess_bridge_used": True,
                    "p64_shell_used": False,
                    "p64_inherited_environment_used": False,
                    "p64_stdin_used": False,
                    "p64_metadata_request_file_used": True,
                    "p64_metadata_request_file_deleted_after_run": True,
                    "p64_launcher_sha256": self.sender_metadata["launcher_sha256"],
                    "p64_sender_program_sha256": self.sender_metadata["sender_program_sha256"],
                    "p64_subprocess_return_code": completed.returncode,
                    "p64_stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                    "p64_stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                }
            )
            result["p64_opaque_sender_subprocess_bridge_result_sha256"] = _sha256_json(result)
            return result

    def execute_real_order_submit(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        del args, kwargs
        raise AdapterPackageDisabledError(
            "P64_REAL_ORDER_SUBMIT_DISABLED_ORDER_TEST_SUBPROCESS_BRIDGE_ONLY"
        )


def _fixture_sender_program_text() -> str:
    return """from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--request-file', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.request_file).read_text(encoding='utf-8'))
request = payload['request_descriptor']
request_sha = request['p61_order_test_request_descriptor_sha256']
redacted = {
    'status_code': 200,
    'accepted_by_fixture': True,
    'response_shape': 'empty_object_equivalent_fixture',
    'request_descriptor_sha256': request_sha,
}
redacted_bytes = json.dumps(redacted, sort_keys=True, separators=(',', ':')).encode('utf-8')
result = {
    'artifact_type': 'p64_no_network_subprocess_sender_result_fixture',
    'environment': 'testnet',
    'base_url': 'https://demo-fapi.binance.com',
    'method': 'POST',
    'path': '/fapi/v1/order/test',
    'test_endpoint_only': True,
    'redacted_response_only': True,
    'redacted_response_sha256': hashlib.sha256(redacted_bytes).hexdigest(),
    'request_descriptor_sha256': request_sha,
    'fixture_executor_used': True,
    'real_external_executor_used': False,
    'http_request_sent': False,
    'signature_created_in_external_process': False,
    'order_test_endpoint_called': False,
    'raw_response_included': False,
    'raw_request_included': False,
    'raw_signed_payload_included': False,
    'credential_value_exposed': False,
    'order_created': False,
    'actual_order_submission_performed': False,
    'real_order_endpoint_called': False,
    'status_endpoint_called': False,
    'cancel_endpoint_called': False,
}
print(json.dumps(result, sort_keys=True, separators=(',', ':')))
"""


def build_p64_no_network_subprocess_bridge_self_test() -> dict[str, Any]:
    request = P61OrderTestRequestDescriptor().to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256="7" * 64,
        api_key_fingerprint_sha256="8" * 64,
    )
    with tempfile.TemporaryDirectory(prefix="p64_fixture_sender_") as tmp:
        script = Path(tmp) / "fixture_sender.py"
        script.write_text(_fixture_sender_program_text(), encoding="utf-8")
        sender_metadata = P64SubprocessSenderMetadata(
            sender_id="P64_NO_NETWORK_SUBPROCESS_SENDER_FIXTURE",
            concrete_external_component=False,
            fixture_only=True,
            launcher_path=str(Path(sys.executable).resolve()),
            launcher_sha256=_sha256_file(Path(sys.executable).resolve()),
            sender_program_path=str(script.resolve()),
            sender_program_sha256=_sha256_file(script.resolve()),
            signing_capable=False,
            network_send_capable=False,
        ).to_dict()
        source_p63 = "1" * 64
        p63_request = "2" * 64
        nonce = "3" * 64
        activation = P64SubprocessBridgeActivation(
            activation_scope=P64_NO_NETWORK_SELF_TEST_SCOPE,
            exact_operator_phrase=EXACT_P64_OPERATOR_BRIDGE_PHRASE,
            operator_confirmation_sha256="4" * 64,
            source_p63_report_sha256=source_p63,
            p63_integration_request_sha256=p63_request,
            p61_request_descriptor_sha256=request["p61_order_test_request_descriptor_sha256"],
            one_shot_nonce_sha256=nonce,
            bridge_enabled=True,
            subprocess_execution_enabled=True,
            sender_program_injection_enabled=True,
            evidence_capture_enabled=True,
            no_secret_scan_enabled=True,
            executable_hashes_validated=True,
            separate_operator_approval_validated=True,
            one_shot_guard_validated=True,
            fixture_only=True,
        ).to_dict()
        bridge_request = P64SubprocessBridgeRequest(
            execution_scope=P64_NO_NETWORK_SELF_TEST_SCOPE,
            bridge_requested=True,
            fixture_only=True,
            credential_reference_id=key_binding.secret_reference_id,
            key_fingerprint_sha256=key_binding.key_fingerprint_sha256,
            source_p63_report_sha256=source_p63,
            p63_integration_request_sha256=p63_request,
            p61_request_descriptor_sha256=request["p61_order_test_request_descriptor_sha256"],
            sender_metadata_sha256=sender_metadata["p64_subprocess_sender_metadata_sha256"],
            one_shot_nonce_sha256=nonce,
        ).to_dict()
        bridge = P64OpaqueSenderSubprocessBridge(
            activation=activation,
            sender_metadata=sender_metadata,
            bridge_request=bridge_request,
            key_binding=key_binding,
        )
        result = bridge.send_signed_order_test(
            request_descriptor=request,
            credential_reference_id=key_binding.secret_reference_id,
        )
        result_validation = validate_redacted_order_test_result(result)
        report = {
            "artifact_type": "p64_no_network_subprocess_bridge_self_test_report",
            "self_test_passed": bool(
                result_validation["redacted_order_test_result_valid"]
                and result.get("p64_subprocess_bridge_used") is True
                and result.get("fixture_executor_used") is True
                and result.get("http_request_sent") is False
                and result.get("signature_created_in_external_process") is False
                and result.get("order_test_endpoint_called") is False
            ),
            "subprocess_bridge_used": True,
            "fixture_sender_program_generated_ephemerally": True,
            "fixture_sender_program_packaged": False,
            "launcher_hash_validated": True,
            "sender_program_hash_validated": True,
            "shell_used": False,
            "inherited_environment_used": False,
            "stdin_used": False,
            "metadata_request_file_used": True,
            "metadata_request_file_deleted_after_run": True,
            "stdout_redacted_json_only": True,
            "stderr_empty": True,
            "fixture_executor_used": True,
            "real_external_executor_used": False,
            "concrete_network_sender_used": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "order_test_endpoint_call_performed": False,
            "actual_order_submission_performed": False,
            "p61_request_descriptor_sha256": request["p61_order_test_request_descriptor_sha256"],
            "p64_sender_metadata_sha256": sender_metadata["p64_subprocess_sender_metadata_sha256"],
            "p64_activation_sha256": activation["p64_subprocess_bridge_activation_sha256"],
            "p64_bridge_request_sha256": bridge_request["p64_subprocess_bridge_request_sha256"],
            "p64_result_sha256": result["p64_opaque_sender_subprocess_bridge_result_sha256"],
        }
        report["p64_no_network_subprocess_bridge_self_test_report_sha256"] = _sha256_json(report)
        return report


def build_p64_negative_fixture_results() -> dict[str, Any]:
    base_metadata = P64SubprocessSenderMetadata().to_dict()
    fixtures: dict[str, Mapping[str, Any]] = {
        "policy_bridge_enabled": validate_subprocess_bridge_policy(
            replace(P64SubprocessBridgePolicy(), bridge_enabled=True).to_dict()
        ),
        "policy_shell_allowed": validate_subprocess_bridge_policy(
            replace(P64SubprocessBridgePolicy(), shell_allowed=True).to_dict()
        ),
        "policy_inherited_environment_allowed": validate_subprocess_bridge_policy(
            replace(P64SubprocessBridgePolicy(), inherited_environment_allowed=True).to_dict()
        ),
        "manifest_runtime_candidate_inclusion": validate_subprocess_bridge_manifest(
            replace(P64SubprocessBridgePackageManifest(), included_in_default_runtime_candidate=True).to_dict()
        ),
        "manifest_concrete_sender_included": validate_subprocess_bridge_manifest(
            replace(P64SubprocessBridgePackageManifest(), concrete_network_sender_program_included=True).to_dict()
        ),
        "sender_mainnet": validate_subprocess_sender_metadata(
            replace(P64SubprocessSenderMetadata(), base_url="https://fapi.binance.com").to_dict(),
            allow_fixture=False,
            require_paths=False,
        ),
        "sender_credential_exposure": validate_subprocess_sender_metadata(
            replace(P64SubprocessSenderMetadata(), raw_credential_exposed_to_bridge=True).to_dict(),
            allow_fixture=False,
            require_paths=False,
        ),
        "activation_runtime_authority": validate_subprocess_bridge_activation(
            replace(P64SubprocessBridgeActivation(), runtime_authority_granted=True).to_dict(),
            require_enabled=False,
            allow_fixture=True,
        ),
        "request_real_submit": validate_subprocess_bridge_request(
            replace(P64SubprocessBridgeRequest(), real_order_submit_requested=True).to_dict(),
            require_requested=False,
            allow_fixture=True,
        ),
        "request_raw_credential": validate_subprocess_bridge_request(
            replace(P64SubprocessBridgeRequest(), raw_credential_included=True).to_dict(),
            require_requested=False,
            allow_fixture=True,
        ),
    }
    results: dict[str, Any] = {}
    for name, validation in fixtures.items():
        valid = any(
            value is True
            for key, value in validation.items()
            if key.endswith("_valid")
        )
        reasons = next(
            (value for key, value in validation.items() if key.endswith("_block_reasons")),
            [],
        )
        results[name] = {
            "blocked_fail_closed": not valid and bool(reasons),
            "block_reasons": reasons,
        }
    report = {
        "artifact_type": "p64_subprocess_bridge_negative_fixture_results",
        "fixture_count": len(results),
        "all_negative_fixtures_blocked_fail_closed": all(
            item["blocked_fail_closed"] for item in results.values()
        ),
        "fixture_results": results,
        "base_sender_metadata_sha256": base_metadata["p64_subprocess_sender_metadata_sha256"],
    }
    report["p64_subprocess_bridge_negative_fixture_results_sha256"] = _sha256_json(report)
    return report


def build_p64_subprocess_bridge_package_report() -> dict[str, Any]:
    policy = P64SubprocessBridgePolicy().to_dict()
    manifest = P64SubprocessBridgePackageManifest().to_dict()
    sender_metadata = P64SubprocessSenderMetadata().to_dict()
    activation = P64SubprocessBridgeActivation().to_dict()
    request = P64SubprocessBridgeRequest().to_dict()
    policy_validation = validate_subprocess_bridge_policy(policy)
    manifest_validation = validate_subprocess_bridge_manifest(manifest)
    sender_validation = validate_subprocess_sender_metadata(
        sender_metadata, allow_fixture=False, require_paths=False
    )
    activation_validation = validate_subprocess_bridge_activation(
        activation, require_enabled=False, allow_fixture=True
    )
    request_validation = validate_subprocess_bridge_request(
        request, require_requested=False, allow_fixture=True
    )
    self_test = build_p64_no_network_subprocess_bridge_self_test()
    negatives = build_p64_negative_fixture_results()
    blockers = _collect_blockers(
        policy_validation,
        manifest_validation,
        sender_validation,
        activation_validation,
        request_validation,
    )
    if not self_test["self_test_passed"]:
        blockers.append("P64_NO_NETWORK_SUBPROCESS_BRIDGE_SELF_TEST_FAILED")
    if not negatives["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("P64_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    report = {
        "artifact_type": "p64_opaque_sender_subprocess_bridge_package_report",
        "status": STATUS_BRIDGE_BLOCKED_FAIL_CLOSED if blockers else STATUS_BRIDGE_VALIDATED_DISABLED,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p64_version": P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_VERSION,
        "policy": policy,
        "package_manifest": manifest,
        "sender_metadata_template": sender_metadata,
        "activation_template": activation,
        "bridge_request_template": request,
        "no_network_self_test": self_test,
        "negative_fixture_results": negatives,
        "subprocess_bridge_implemented": True,
        "metadata_only_request_file_implemented": True,
        "executable_hash_attestation_implemented": True,
        "minimal_environment_implemented": True,
        "shell_disabled": True,
        "stdin_disabled": True,
        "concrete_network_sender_program_included": False,
        "credential_reader_included": False,
        "secret_file_reader_included": False,
        "secret_file_writer_included": False,
        "subprocess_bridge_enabled": False,
        "subprocess_execution_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "order_test_endpoint_call_enabled": False,
        "order_test_endpoint_call_performed": False,
        "real_order_submit_enabled": False,
        "real_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
        "actual_testnet_order_submitted": False,
        "actual_live_order_submitted": False,
        "runtime_authority_granted": False,
        "runtime_mutation_performed": False,
    }
    report["p64_opaque_sender_subprocess_bridge_package_report_sha256"] = _sha256_json(report)
    return report
