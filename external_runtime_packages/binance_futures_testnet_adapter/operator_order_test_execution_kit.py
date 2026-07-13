from __future__ import annotations

import json
import os
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
    ALLOWED_REAL_ORDER_TEST_SCOPE,
    EXACT_ORDER_TEST_APPROVAL_PHRASE,
    NO_NETWORK_SELF_TEST_SCOPE,
    P61ExternalRuntimeActivation,
    P61ExternalSignedOrderTestExecutor,
    P61NoNetworkInjectedExecutor,
    P61OperatorOrderTestApproval,
    P61OrderTestRequestDescriptor,
    RealTestnetOrderTestDryValidationAdapter,
    validate_external_runtime_activation,
    validate_operator_order_test_approval,
    validate_order_test_request_descriptor,
    validate_redacted_order_test_result,
)

P62_OPERATOR_ORDER_TEST_EXECUTION_KIT_VERSION = "p62_operator_order_test_execution_kit_v1"
STATUS_KIT_VALIDATED_DISABLED = (
    "P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_KIT_BLOCKED_FAIL_CLOSED = (
    "P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_BLOCKED_FAIL_CLOSED"
)

EXACT_P62_OPERATOR_KIT_PHRASE = (
    "AUTHORIZE ONE OPERATOR SIDE BINANCE FUTURES TESTNET ORDER TEST RUN ONLY"
)
P62_NO_NETWORK_SELF_TEST_SCOPE = "p62_no_network_operator_execution_kit_self_test"
P62_APPROVED_EXTERNAL_RUNTIME_SCOPE = "p62_approved_operator_side_order_test_once"


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
                    "raw_signed_payload",
                    "raw_request_body",
                    "unredacted_exchange_response",
                    "credential_value",
                )
            ):
                blockers.append(f"P62_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, prefix=child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
    return blockers


def _validation_blockers(*validations: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for validation in validations:
        for key, value in validation.items():
            if key.endswith("_block_reasons") and isinstance(value, list):
                blockers.extend(str(item) for item in value)
    return sorted(dict.fromkeys(blockers))


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


@dataclass(frozen=True)
class P62OperatorExecutionKitPolicy:
    policy_version: str = "p62_operator_execution_kit_policy_v1"
    package_scope: str = "separate_operator_external_runtime_package_only"
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    symbol: str = ALLOWED_SYMBOL
    max_run_count: int = 1
    one_shot_guard_required: bool = True
    exact_operator_phrase_required: bool = True
    separate_p61_approval_required: bool = True
    external_process_only: bool = True
    metadata_only_credential_reference_required: bool = True
    process_memory_credential_binding_required: bool = True
    redacted_evidence_only: bool = True
    no_secret_scan_required: bool = True
    evidence_manifest_required: bool = True
    kit_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    order_test_call_enabled: bool = False
    real_order_submit_enabled: bool = False
    status_polling_enabled: bool = False
    cancel_enabled: bool = False
    concrete_executor_included: bool = False
    credential_reader_included: bool = False
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    raw_request_persistence_allowed: bool = False
    raw_response_persistence_allowed: bool = False
    runtime_authority_granted: bool = False
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p62_operator_execution_kit_policy_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P62OperatorExecutionKitManifest:
    manifest_version: str = "p62_operator_execution_kit_manifest_v1"
    kit_id: str = "p62_operator_side_external_order_test_execution_kit"
    package_scope: str = "separate_operator_external_runtime_package_only"
    external_runtime_only: bool = True
    included_in_source_handoff: bool = True
    included_in_external_adapter_package: bool = True
    included_in_default_runtime_candidate: bool = False
    one_shot_guard_implemented: bool = True
    redacted_evidence_exporter_implemented: bool = True
    no_secret_scanner_implemented: bool = True
    p58_bridge_exporter_implemented: bool = True
    concrete_executor_included: bool = False
    credential_reader_included: bool = False
    secret_file_reader_included: bool = False
    secret_file_writer_included: bool = False
    order_submit_capability_included: bool = False
    enabled_by_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p62_operator_execution_kit_manifest_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P62OperatorRunRequest:
    request_version: str = "p62_operator_run_request_v1"
    execution_scope: str = "p62_review_only_disabled"
    exact_operator_phrase: str = ""
    operator_confirmation_sha256: str = "0" * 64
    source_p61_report_sha256: str = "0" * 64
    p61_request_descriptor_sha256: str = "0" * 64
    p61_operator_approval_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64
    credential_reference_id: str = "OPERATOR_SUPPLIED_TESTNET_CREDENTIAL_REFERENCE_ID"
    key_fingerprint_sha256: str = "0" * 64
    requested_output_reference: str = "operator_evidence_output"
    run_requested: bool = False
    operator_approval_validated: bool = False
    p61_approval_validated: bool = False
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
        payload["p62_operator_run_request_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P62OperatorExecutionActivation:
    activation_version: str = "p62_operator_execution_activation_v1"
    activation_scope: str = "p62_review_only_disabled"
    kit_enabled: bool = False
    one_shot_guard_enabled: bool = False
    external_executor_injection_enabled: bool = False
    network_calls_enabled: bool = False
    signing_enabled: bool = False
    order_test_call_enabled: bool = False
    evidence_export_enabled: bool = False
    no_secret_scan_enabled: bool = False
    real_order_submit_enabled: bool = False
    one_request_only: bool = True
    testnet_only: bool = True
    order_test_only: bool = True
    separate_operator_approval_validated: bool = False
    fixture_only: bool = False
    runtime_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p62_operator_execution_activation_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P62EvidenceExportPolicy:
    policy_version: str = "p62_evidence_export_policy_v1"
    redacted_result_required: bool = True
    execution_transcript_required: bool = True
    no_secret_scan_required: bool = True
    p58_bridge_candidate_required: bool = True
    evidence_manifest_required: bool = True
    hash_every_artifact: bool = True
    atomic_write_required: bool = True
    raw_request_allowed: bool = False
    raw_response_allowed: bool = False
    raw_signed_payload_allowed: bool = False
    raw_credential_allowed: bool = False
    secret_file_allowed: bool = False
    unredacted_exchange_response_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p62_evidence_export_policy_sha256"] = _sha256_json(payload)
        return payload


class P62OneShotRunGuard:
    """Filesystem one-shot marker using O_EXCL. The marker contains hashes only."""

    def __init__(self, marker_path: Path) -> None:
        self.marker_path = marker_path

    def acquire(self, *, nonce_sha256: str, request_sha256: str) -> dict[str, Any]:
        if not _is_sha256_hex(nonce_sha256) or not _is_sha256_hex(request_sha256):
            raise AdapterPackageValidationError("P62_ONE_SHOT_GUARD_HASH_INVALID")
        self.marker_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "artifact_type": "p62_one_shot_run_guard_marker",
            "nonce_sha256": nonce_sha256,
            "request_sha256": request_sha256,
            "contains_secret_value": False,
            "contains_raw_request": False,
        }
        payload["p62_one_shot_run_guard_marker_sha256"] = _sha256_json(payload)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(self.marker_path, flags, 0o600)
        except FileExistsError as exc:
            raise AdapterPackageValidationError("P62_ONE_SHOT_GUARD_ALREADY_ACQUIRED") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return payload

    def release_after_failure(self) -> None:
        self.marker_path.unlink(missing_ok=True)



def validate_operator_execution_kit_policy(
    policy: Mapping[str, Any] | P62OperatorExecutionKitPolicy | None,
) -> dict[str, Any]:
    payload = policy.to_dict() if isinstance(policy, P62OperatorExecutionKitPolicy) else dict(policy or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p62_operator_execution_kit_policy_sha256"):
        blockers.append("P62_POLICY_EMBEDDED_SHA256_INVALID")
    expected = {
        "package_scope": "separate_operator_external_runtime_package_only",
        "environment": ALLOWED_ENVIRONMENT,
        "venue": ALLOWED_VENUE,
        "base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "method": "POST",
        "path": ALLOWED_ENDPOINTS["test_submit"],
        "symbol": ALLOWED_SYMBOL,
        "max_run_count": 1,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            blockers.append(f"P62_POLICY_{key.upper()}_INVALID")
    for key in (
        "one_shot_guard_required",
        "exact_operator_phrase_required",
        "separate_p61_approval_required",
        "external_process_only",
        "metadata_only_credential_reference_required",
        "process_memory_credential_binding_required",
        "redacted_evidence_only",
        "no_secret_scan_required",
        "evidence_manifest_required",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P62_POLICY_{key.upper()}_NOT_TRUE")
    for key in (
        "kit_enabled",
        "network_calls_enabled",
        "signing_enabled",
        "order_test_call_enabled",
        "real_order_submit_enabled",
        "status_polling_enabled",
        "cancel_enabled",
        "concrete_executor_included",
        "credential_reader_included",
        "credential_persistence_allowed",
        "credential_logging_allowed",
        "raw_request_persistence_allowed",
        "raw_response_persistence_allowed",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P62_POLICY_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "operator_execution_kit_policy_valid": not blockers,
        "operator_execution_kit_policy_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    result["p62_operator_execution_kit_policy_validation_sha256"] = _sha256_json(result)
    return result


def validate_operator_execution_kit_manifest(
    manifest: Mapping[str, Any] | P62OperatorExecutionKitManifest | None,
) -> dict[str, Any]:
    payload = manifest.to_dict() if isinstance(manifest, P62OperatorExecutionKitManifest) else dict(manifest or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p62_operator_execution_kit_manifest_sha256"):
        blockers.append("P62_MANIFEST_EMBEDDED_SHA256_INVALID")
    for key in (
        "external_runtime_only",
        "included_in_source_handoff",
        "included_in_external_adapter_package",
        "one_shot_guard_implemented",
        "redacted_evidence_exporter_implemented",
        "no_secret_scanner_implemented",
        "p58_bridge_exporter_implemented",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P62_MANIFEST_{key.upper()}_NOT_TRUE")
    for key in (
        "included_in_default_runtime_candidate",
        "concrete_executor_included",
        "credential_reader_included",
        "secret_file_reader_included",
        "secret_file_writer_included",
        "order_submit_capability_included",
        "enabled_by_default",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P62_MANIFEST_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "operator_execution_kit_manifest_valid": not blockers,
        "operator_execution_kit_manifest_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    result["p62_operator_execution_kit_manifest_validation_sha256"] = _sha256_json(result)
    return result


def validate_operator_run_request(
    request: Mapping[str, Any] | P62OperatorRunRequest | None,
    *,
    require_run: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = request.to_dict() if isinstance(request, P62OperatorRunRequest) else dict(request or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p62_operator_run_request_sha256"):
        blockers.append("P62_RUN_REQUEST_EMBEDDED_SHA256_INVALID")
    if require_run:
        expected_scope = P62_NO_NETWORK_SELF_TEST_SCOPE if allow_fixture else P62_APPROVED_EXTERNAL_RUNTIME_SCOPE
        if payload.get("execution_scope") != expected_scope:
            blockers.append("P62_RUN_REQUEST_EXECUTION_SCOPE_INVALID")
        if payload.get("exact_operator_phrase") != EXACT_P62_OPERATOR_KIT_PHRASE:
            blockers.append("P62_RUN_REQUEST_OPERATOR_PHRASE_INVALID")
        for key in (
            "operator_confirmation_sha256",
            "source_p61_report_sha256",
            "p61_request_descriptor_sha256",
            "p61_operator_approval_sha256",
            "one_shot_nonce_sha256",
            "key_fingerprint_sha256",
        ):
            if not _is_sha256_hex(payload.get(key)) or payload.get(key) == "0" * 64:
                blockers.append(f"P62_RUN_REQUEST_{key.upper()}_INVALID")
        for key in ("run_requested", "operator_approval_validated", "p61_approval_validated"):
            if payload.get(key) is not True:
                blockers.append(f"P62_RUN_REQUEST_{key.upper()}_NOT_TRUE")
    else:
        if payload.get("execution_scope") != "p62_review_only_disabled":
            blockers.append("P62_RUN_REQUEST_DISABLED_SCOPE_INVALID")
        if payload.get("run_requested") is not False:
            blockers.append("P62_RUN_REQUEST_RUN_REQUESTED_NOT_FALSE")
        if payload.get("exact_operator_phrase") not in ("", "OPERATOR_TO_FILL"):
            blockers.append("P62_RUN_REQUEST_TEMPLATE_OPERATOR_PHRASE_INVALID")
    if payload.get("fixture_only") is True and not allow_fixture:
        blockers.append("P62_RUN_REQUEST_FIXTURE_NOT_ALLOWED_FOR_REAL_PATH")
    for key in ("testnet_only", "order_test_only", "one_request_only"):
        if payload.get(key) is not True:
            blockers.append(f"P62_RUN_REQUEST_{key.upper()}_NOT_TRUE")
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
            blockers.append(f"P62_RUN_REQUEST_{key.upper()}_NOT_FALSE")
    output_ref = str(payload.get("requested_output_reference") or "")
    if not output_ref or output_ref.startswith(("/", "\\")) or ".." in Path(output_ref).parts:
        blockers.append("P62_RUN_REQUEST_OUTPUT_REFERENCE_UNSAFE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "operator_run_request_valid": not blockers,
        "operator_run_request_block_reasons": sorted(dict.fromkeys(blockers)),
        "run_requested": payload.get("run_requested") is True,
        "fixture_only": payload.get("fixture_only") is True,
    }
    result["p62_operator_run_request_validation_sha256"] = _sha256_json(result)
    return result


def validate_operator_execution_activation(
    activation: Mapping[str, Any] | P62OperatorExecutionActivation | None,
    *,
    require_enabled: bool,
    allow_fixture: bool,
) -> dict[str, Any]:
    payload = activation.to_dict() if isinstance(activation, P62OperatorExecutionActivation) else dict(activation or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p62_operator_execution_activation_sha256"):
        blockers.append("P62_ACTIVATION_EMBEDDED_SHA256_INVALID")
    if require_enabled:
        expected_scope = P62_NO_NETWORK_SELF_TEST_SCOPE if allow_fixture else P62_APPROVED_EXTERNAL_RUNTIME_SCOPE
        if payload.get("activation_scope") != expected_scope:
            blockers.append("P62_ACTIVATION_SCOPE_INVALID")
        for key in (
            "kit_enabled",
            "one_shot_guard_enabled",
            "external_executor_injection_enabled",
            "network_calls_enabled",
            "signing_enabled",
            "order_test_call_enabled",
            "evidence_export_enabled",
            "no_secret_scan_enabled",
            "one_request_only",
            "testnet_only",
            "order_test_only",
            "separate_operator_approval_validated",
        ):
            if payload.get(key) is not True:
                blockers.append(f"P62_ACTIVATION_{key.upper()}_NOT_TRUE")
    else:
        if payload.get("activation_scope") != "p62_review_only_disabled":
            blockers.append("P62_ACTIVATION_DISABLED_SCOPE_INVALID")
        for key in (
            "kit_enabled",
            "one_shot_guard_enabled",
            "external_executor_injection_enabled",
            "network_calls_enabled",
            "signing_enabled",
            "order_test_call_enabled",
            "evidence_export_enabled",
            "no_secret_scan_enabled",
            "separate_operator_approval_validated",
            "fixture_only",
        ):
            if payload.get(key) is not False:
                blockers.append(f"P62_ACTIVATION_{key.upper()}_NOT_FALSE")
    if payload.get("real_order_submit_enabled") is not False:
        blockers.append("P62_ACTIVATION_REAL_ORDER_SUBMIT_ENABLED_NOT_FALSE")
    if payload.get("runtime_authority_granted") is not False:
        blockers.append("P62_ACTIVATION_RUNTIME_AUTHORITY_GRANTED_NOT_FALSE")
    if payload.get("fixture_only") is True and not allow_fixture:
        blockers.append("P62_ACTIVATION_FIXTURE_NOT_ALLOWED_FOR_REAL_PATH")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "operator_execution_activation_valid": not blockers,
        "operator_execution_activation_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    result["p62_operator_execution_activation_validation_sha256"] = _sha256_json(result)
    return result


def validate_evidence_export_policy(
    policy: Mapping[str, Any] | P62EvidenceExportPolicy | None,
) -> dict[str, Any]:
    payload = policy.to_dict() if isinstance(policy, P62EvidenceExportPolicy) else dict(policy or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p62_evidence_export_policy_sha256"):
        blockers.append("P62_EXPORT_POLICY_EMBEDDED_SHA256_INVALID")
    for key in (
        "redacted_result_required",
        "execution_transcript_required",
        "no_secret_scan_required",
        "p58_bridge_candidate_required",
        "evidence_manifest_required",
        "hash_every_artifact",
        "atomic_write_required",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P62_EXPORT_POLICY_{key.upper()}_NOT_TRUE")
    for key in (
        "raw_request_allowed",
        "raw_response_allowed",
        "raw_signed_payload_allowed",
        "raw_credential_allowed",
        "secret_file_allowed",
        "unredacted_exchange_response_allowed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P62_EXPORT_POLICY_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "evidence_export_policy_valid": not blockers,
        "evidence_export_policy_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    result["p62_evidence_export_policy_validation_sha256"] = _sha256_json(result)
    return result


def _build_no_secret_scan(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    matches: list[str] = []
    for name, payload in artifacts.items():
        for match in _walk_forbidden(payload):
            matches.append(f"{name}:{match}")
    report = {
        "artifact_type": "p62_no_secret_scan_report",
        "scan_completed": True,
        "scan_passed": not matches,
        "match_count": len(matches),
        "matches": sorted(matches),
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
    }
    report["p62_no_secret_scan_report_sha256"] = _sha256_json(report)
    return report


def export_p62_redacted_evidence_bundle(
    *,
    output_dir: Path,
    run_request: Mapping[str, Any],
    p61_request: Mapping[str, Any],
    redacted_result: Mapping[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_validation = validate_redacted_order_test_result(redacted_result)
    if not result_validation["redacted_order_test_result_valid"]:
        raise AdapterPackageValidationError(
            ";".join(result_validation["redacted_order_test_result_block_reasons"])
        )
    suffix = "NO_NETWORK_SELF_TEST" if fixture_only else "REDACTED_EXTERNAL_RUNTIME"
    redacted = {
        "artifact_type": "p62_redacted_order_test_result",
        "fixture_only": fixture_only,
        "real_signed_testnet_evidence": False,
        "order_test_evidence_only": True,
        "p7_import_eligible": False,
        "request_descriptor_sha256": p61_request.get("p61_order_test_request_descriptor_sha256"),
        "redacted_response_sha256": redacted_result.get("redacted_response_sha256"),
        "http_request_sent": redacted_result.get("http_request_sent") is True,
        "signature_created_in_external_process": redacted_result.get(
            "signature_created_in_external_process"
        ) is True,
        "order_test_endpoint_called": redacted_result.get("order_test_endpoint_called") is True,
        "order_created": False,
        "actual_order_submission_performed": False,
        "raw_request_included": False,
        "raw_response_included": False,
        "raw_signed_payload_included": False,
        "credential_value_exposed": False,
    }
    redacted["p62_redacted_order_test_result_sha256"] = _sha256_json(redacted)
    transcript = {
        "artifact_type": "p62_operator_execution_transcript",
        "fixture_only": fixture_only,
        "execution_scope": run_request.get("execution_scope"),
        "operator_run_request_sha256": run_request.get("p62_operator_run_request_sha256"),
        "one_shot_nonce_sha256": run_request.get("one_shot_nonce_sha256"),
        "credential_reference_id": run_request.get("credential_reference_id"),
        "key_fingerprint_sha256": run_request.get("key_fingerprint_sha256"),
        "testnet_only": True,
        "order_test_only": True,
        "one_request_only": True,
        "real_order_submit_allowed": False,
        "raw_credential_included": False,
        "runtime_authority_granted": False,
    }
    transcript["p62_operator_execution_transcript_sha256"] = _sha256_json(transcript)
    bridge = {
        "artifact_type": "p62_p58_bridge_candidate",
        "source_phase": "p62_operator_side_order_test_execution_kit",
        "fixture_only": fixture_only,
        "synthetic_or_sample_evidence": fixture_only,
        "real_signed_testnet_evidence": False,
        "p58_acquisition_eligible": False,
        "p7_import_eligible": False,
        "redacted_result_sha256": redacted["p62_redacted_order_test_result_sha256"],
        "execution_transcript_sha256": transcript[
            "p62_operator_execution_transcript_sha256"
        ],
        "order_created": False,
        "actual_order_submission_performed": False,
    }
    bridge["p62_p58_bridge_candidate_sha256"] = _sha256_json(bridge)
    artifacts: dict[str, Mapping[str, Any]] = {
        f"p62_redacted_order_test_result_{suffix}.json": redacted,
        f"p62_operator_execution_transcript_{suffix}.json": transcript,
        f"p62_p58_bridge_candidate_{suffix}.json": bridge,
    }
    scan = _build_no_secret_scan(artifacts)
    artifacts[f"p62_no_secret_scan_report_{suffix}.json"] = scan
    if not scan["scan_passed"]:
        raise AdapterPackageValidationError("P62_NO_SECRET_SCAN_FAILED")
    manifest = {
        "artifact_type": "p62_redacted_evidence_export_manifest",
        "fixture_only": fixture_only,
        "redacted_only": True,
        "artifact_count": len(artifacts),
        "artifact_sha256_by_name": {
            name: _sha256_json(payload) for name, payload in sorted(artifacts.items())
        },
        "raw_request_included": False,
        "raw_response_included": False,
        "raw_signed_payload_included": False,
        "secret_value_included": False,
        "actual_order_submission_performed": False,
    }
    manifest["p62_redacted_evidence_export_manifest_sha256"] = _sha256_json(manifest)
    artifacts[f"p62_redacted_evidence_export_manifest_{suffix}.json"] = manifest
    for name, payload in artifacts.items():
        _atomic_write_json(output_dir / name, payload)
    return {
        "artifact_type": "p62_redacted_evidence_export_result",
        "export_completed": True,
        "fixture_only": fixture_only,
        "output_file_count": len(artifacts),
        "output_filenames": sorted(artifacts),
        "manifest_sha256": manifest["p62_redacted_evidence_export_manifest_sha256"],
        "no_secret_scan_passed": scan["scan_passed"],
        "p58_bridge_candidate_created": True,
        "p58_acquisition_eligible": False,
        "p7_import_eligible": False,
        "actual_order_submission_performed": False,
    }


class OperatorSideExternalOrderTestExecutionKit:
    kit_id = "p62_operator_side_external_order_test_execution_kit"
    kit_version = P62_OPERATOR_ORDER_TEST_EXECUTION_KIT_VERSION

    def __init__(
        self,
        *,
        policy: P62OperatorExecutionKitPolicy | None = None,
        key_binding: MetadataOnlyKeyBinding | None = None,
    ) -> None:
        self.policy = policy or P62OperatorExecutionKitPolicy()
        self.key_binding = key_binding or MetadataOnlyKeyBinding(
            key_fingerprint_sha256=_sha256_json({"p62": "metadata-only-key-fingerprint"}),
            api_key_fingerprint_sha256=_sha256_json({"p62": "metadata-only-api-key-fingerprint"}),
        )
        self.p61_adapter = RealTestnetOrderTestDryValidationAdapter(key_binding=self.key_binding)

    def run_no_network_operator_kit_self_test(self) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="p62_operator_kit_") as tmp:
            root = Path(tmp)
            p61_request = P61OrderTestRequestDescriptor().to_dict()
            run_request = P62OperatorRunRequest(
                execution_scope=P62_NO_NETWORK_SELF_TEST_SCOPE,
                exact_operator_phrase=EXACT_P62_OPERATOR_KIT_PHRASE,
                operator_confirmation_sha256="1" * 64,
                source_p61_report_sha256="2" * 64,
                p61_request_descriptor_sha256=p61_request[
                    "p61_order_test_request_descriptor_sha256"
                ],
                p61_operator_approval_sha256="3" * 64,
                one_shot_nonce_sha256="4" * 64,
                credential_reference_id=self.key_binding.secret_reference_id,
                key_fingerprint_sha256=self.key_binding.key_fingerprint_sha256,
                requested_output_reference="operator_evidence_output",
                run_requested=True,
                operator_approval_validated=True,
                p61_approval_validated=True,
                fixture_only=True,
            ).to_dict()
            request_validation = validate_operator_run_request(
                run_request, require_run=True, allow_fixture=True
            )
            activation = P62OperatorExecutionActivation(
                activation_scope=P62_NO_NETWORK_SELF_TEST_SCOPE,
                kit_enabled=True,
                one_shot_guard_enabled=True,
                external_executor_injection_enabled=True,
                network_calls_enabled=True,
                signing_enabled=True,
                order_test_call_enabled=True,
                evidence_export_enabled=True,
                no_secret_scan_enabled=True,
                separate_operator_approval_validated=True,
                fixture_only=True,
            ).to_dict()
            activation_validation = validate_operator_execution_activation(
                activation, require_enabled=True, allow_fixture=True
            )
            blockers = _validation_blockers(request_validation, activation_validation)
            if blockers:
                raise AdapterPackageValidationError(";".join(blockers))
            guard = P62OneShotRunGuard(root / "one_shot_guard.json")
            marker = guard.acquire(
                nonce_sha256=run_request["one_shot_nonce_sha256"],
                request_sha256=run_request["p62_operator_run_request_sha256"],
            )
            duplicate_blocked = False
            try:
                guard.acquire(
                    nonce_sha256=run_request["one_shot_nonce_sha256"],
                    request_sha256=run_request["p62_operator_run_request_sha256"],
                )
            except AdapterPackageValidationError:
                duplicate_blocked = True
            redacted_result = P61NoNetworkInjectedExecutor().execute_signed_order_test(
                request_descriptor=p61_request,
                credential_reference_id=self.key_binding.secret_reference_id,
            )
            export = export_p62_redacted_evidence_bundle(
                output_dir=root / "operator_evidence_output",
                run_request=run_request,
                p61_request=p61_request,
                redacted_result=redacted_result,
                fixture_only=True,
            )
            output_files_exist = all(
                (root / "operator_evidence_output" / name).exists()
                for name in export["output_filenames"]
            )
            report = {
                "artifact_type": "p62_operator_execution_kit_no_network_self_test_report",
                "self_test_passed": bool(
                    request_validation["operator_run_request_valid"]
                    and activation_validation["operator_execution_activation_valid"]
                    and duplicate_blocked
                    and export["export_completed"]
                    and export["no_secret_scan_passed"]
                    and output_files_exist
                ),
                "one_shot_guard_acquired": True,
                "one_shot_guard_marker_sha256": marker[
                    "p62_one_shot_run_guard_marker_sha256"
                ],
                "duplicate_second_run_blocked": duplicate_blocked,
                "redacted_evidence_export_completed": export["export_completed"],
                "redacted_evidence_output_file_count": export["output_file_count"],
                "redacted_evidence_output_files_exist": output_files_exist,
                "no_secret_scan_passed": export["no_secret_scan_passed"],
                "p58_bridge_candidate_created": export["p58_bridge_candidate_created"],
                "p58_acquisition_eligible": False,
                "p7_import_eligible": False,
                "fixture_executor_used": True,
                "real_external_executor_used": False,
                "http_request_sent": False,
                "signature_created": False,
                "secret_value_accessed": False,
                "actual_order_submission_performed": False,
            }
            report["p62_operator_execution_kit_no_network_self_test_report_sha256"] = _sha256_json(report)
            return report

    def execute_approved_external_runtime_once(
        self,
        *,
        run_request: Mapping[str, Any] | P62OperatorRunRequest,
        activation: Mapping[str, Any] | P62OperatorExecutionActivation,
        p61_request: Mapping[str, Any] | P61OrderTestRequestDescriptor,
        p61_approval: Mapping[str, Any] | P61OperatorOrderTestApproval,
        p61_activation: Mapping[str, Any] | P61ExternalRuntimeActivation,
        executor: P61ExternalSignedOrderTestExecutor,
        output_dir: Path,
        guard_path: Path,
    ) -> dict[str, Any]:
        run_payload = run_request.to_dict() if isinstance(run_request, P62OperatorRunRequest) else dict(run_request)
        activation_payload = activation.to_dict() if isinstance(activation, P62OperatorExecutionActivation) else dict(activation)
        p61_request_payload = p61_request.to_dict() if isinstance(p61_request, P61OrderTestRequestDescriptor) else dict(p61_request)
        p61_approval_payload = p61_approval.to_dict() if isinstance(p61_approval, P61OperatorOrderTestApproval) else dict(p61_approval)
        p61_activation_payload = p61_activation.to_dict() if isinstance(p61_activation, P61ExternalRuntimeActivation) else dict(p61_activation)
        validations = [
            validate_operator_run_request(run_payload, require_run=True, allow_fixture=False),
            validate_operator_execution_activation(
                activation_payload, require_enabled=True, allow_fixture=False
            ),
            validate_order_test_request_descriptor(p61_request_payload, allow_fixture=False),
            validate_operator_order_test_approval(
                p61_approval_payload, require_granted=True, allow_fixture=False
            ),
            validate_external_runtime_activation(
                p61_activation_payload, require_enabled=True, allow_fixture=False
            ),
        ]
        blockers = _validation_blockers(*validations)
        if run_payload.get("source_p61_report_sha256") == "0" * 64:
            blockers.append("P62_REAL_RUN_SOURCE_P61_REPORT_SHA256_INVALID")
        if run_payload.get("p61_request_descriptor_sha256") != p61_request_payload.get(
            "p61_order_test_request_descriptor_sha256"
        ):
            blockers.append("P62_REAL_RUN_P61_REQUEST_HASH_MISMATCH")
        if run_payload.get("p61_operator_approval_sha256") != p61_approval_payload.get(
            "p61_operator_order_test_approval_sha256"
        ):
            blockers.append("P62_REAL_RUN_P61_APPROVAL_HASH_MISMATCH")
        if run_payload.get("credential_reference_id") != self.key_binding.secret_reference_id:
            blockers.append("P62_REAL_RUN_CREDENTIAL_REFERENCE_MISMATCH")
        if run_payload.get("key_fingerprint_sha256") != self.key_binding.key_fingerprint_sha256:
            blockers.append("P62_REAL_RUN_KEY_FINGERPRINT_MISMATCH")
        if blockers:
            raise AdapterPackageValidationError(";".join(sorted(dict.fromkeys(blockers))))
        guard = P62OneShotRunGuard(guard_path)
        guard.acquire(
            nonce_sha256=str(run_payload["one_shot_nonce_sha256"]),
            request_sha256=str(run_payload["p62_operator_run_request_sha256"]),
        )
        try:
            result = self.p61_adapter.execute_approved_external_runtime_order_test(
                request=p61_request_payload,
                approval=p61_approval_payload,
                activation=p61_activation_payload,
                executor=executor,
            )
            export = export_p62_redacted_evidence_bundle(
                output_dir=output_dir,
                run_request=run_payload,
                p61_request=p61_request_payload,
                redacted_result=result,
                fixture_only=False,
            )
            return {
                "artifact_type": "p62_operator_execution_kit_run_result",
                "execution_completed": True,
                "one_shot_guard_retained": True,
                "redacted_evidence_export": export,
                "real_order_submit_performed": False,
                "actual_order_submission_performed": False,
            }
        except Exception:
            guard.release_after_failure()
            raise

    def execute_real_order_submit(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        del args, kwargs
        raise AdapterPackageDisabledError(
            "P62_REAL_ORDER_SUBMIT_DISABLED_OPERATOR_KIT_ORDER_TEST_ONLY"
        )


def build_p62_no_network_self_test() -> dict[str, Any]:
    return OperatorSideExternalOrderTestExecutionKit().run_no_network_operator_kit_self_test()


def build_p62_negative_fixture_results() -> dict[str, Any]:
    fixtures: dict[str, Mapping[str, Any]] = {
        "policy_kit_enabled": validate_operator_execution_kit_policy(
            replace(P62OperatorExecutionKitPolicy(), kit_enabled=True).to_dict()
        ),
        "policy_network_enabled": validate_operator_execution_kit_policy(
            replace(P62OperatorExecutionKitPolicy(), network_calls_enabled=True).to_dict()
        ),
        "manifest_runtime_candidate_included": validate_operator_execution_kit_manifest(
            replace(
                P62OperatorExecutionKitManifest(), included_in_default_runtime_candidate=True
            ).to_dict()
        ),
        "manifest_concrete_executor_included": validate_operator_execution_kit_manifest(
            replace(P62OperatorExecutionKitManifest(), concrete_executor_included=True).to_dict()
        ),
        "run_wrong_phrase": validate_operator_run_request(
            replace(
                P62OperatorRunRequest(),
                execution_scope=P62_NO_NETWORK_SELF_TEST_SCOPE,
                exact_operator_phrase="WRONG",
                operator_confirmation_sha256="1" * 64,
                source_p61_report_sha256="2" * 64,
                p61_request_descriptor_sha256="3" * 64,
                p61_operator_approval_sha256="4" * 64,
                one_shot_nonce_sha256="5" * 64,
                key_fingerprint_sha256="6" * 64,
                run_requested=True,
                operator_approval_validated=True,
                p61_approval_validated=True,
                fixture_only=True,
            ).to_dict(),
            require_run=True,
            allow_fixture=True,
        ),
        "run_mainnet_authority": validate_operator_run_request(
            replace(P62OperatorRunRequest(), runtime_authority_granted=True).to_dict(),
            require_run=False,
            allow_fixture=True,
        ),
        "run_unsafe_output_path": validate_operator_run_request(
            replace(P62OperatorRunRequest(), requested_output_reference="../escape").to_dict(),
            require_run=False,
            allow_fixture=True,
        ),
        "activation_real_submit": validate_operator_execution_activation(
            replace(P62OperatorExecutionActivation(), real_order_submit_enabled=True).to_dict(),
            require_enabled=False,
            allow_fixture=True,
        ),
        "export_raw_response": validate_evidence_export_policy(
            replace(P62EvidenceExportPolicy(), raw_response_allowed=True).to_dict()
        ),
        "raw_secret_field": validate_operator_run_request(
            {**P62OperatorRunRequest().to_dict(), "api_secret_value": "DO_NOT_STORE"},
            require_run=False,
            allow_fixture=True,
        ),
    }

    def blocked(item: Mapping[str, Any]) -> bool:
        validity = [value for key, value in item.items() if key.endswith("_valid")]
        return bool(validity) and all(value is False for value in validity)

    report = {
        "artifact_type": "p62_operator_execution_kit_negative_fixture_results",
        "fixture_results": fixtures,
        "fixture_count": len(fixtures),
        "all_negative_fixtures_blocked_fail_closed": all(
            blocked(item) for item in fixtures.values()
        ),
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    report["p62_operator_execution_kit_negative_fixture_results_sha256"] = _sha256_json(report)
    return report


def build_p62_operator_execution_kit_package_report() -> dict[str, Any]:
    policy = P62OperatorExecutionKitPolicy().to_dict()
    manifest = P62OperatorExecutionKitManifest().to_dict()
    run_template = P62OperatorRunRequest().to_dict()
    activation_template = P62OperatorExecutionActivation().to_dict()
    export_policy = P62EvidenceExportPolicy().to_dict()
    validations = {
        "policy": validate_operator_execution_kit_policy(policy),
        "manifest": validate_operator_execution_kit_manifest(manifest),
        "run_template": validate_operator_run_request(
            run_template, require_run=False, allow_fixture=True
        ),
        "activation_template": validate_operator_execution_activation(
            activation_template, require_enabled=False, allow_fixture=True
        ),
        "export_policy": validate_evidence_export_policy(export_policy),
    }
    self_test = build_p62_no_network_self_test()
    negatives = build_p62_negative_fixture_results()
    blockers = _validation_blockers(*validations.values())
    if not self_test["self_test_passed"]:
        blockers.append("P62_NO_NETWORK_SELF_TEST_FAILED")
    if not negatives["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("P62_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    status = STATUS_KIT_BLOCKED_FAIL_CLOSED if blockers else STATUS_KIT_VALIDATED_DISABLED
    report = {
        "artifact_type": "p62_operator_execution_kit_package_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "package_version": P62_OPERATOR_ORDER_TEST_EXECUTION_KIT_VERSION,
        "policy": policy,
        "manifest": manifest,
        "operator_run_request_template": run_template,
        "operator_execution_activation_template": activation_template,
        "evidence_export_policy": export_policy,
        "validations": validations,
        "no_network_self_test": self_test,
        "negative_fixture_results": negatives,
        "operator_execution_kit_implemented": True,
        "one_shot_run_guard_implemented": True,
        "redacted_evidence_exporter_implemented": True,
        "p58_bridge_exporter_implemented": True,
        "external_executor_injection_contract_implemented": True,
        "operator_execution_kit_enabled": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_submit_enabled": False,
        "real_order_submit_performed": False,
        "concrete_external_executor_included": False,
        "credential_reader_included": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    report["p62_operator_execution_kit_package_report_sha256"] = _sha256_json(report)
    return report
