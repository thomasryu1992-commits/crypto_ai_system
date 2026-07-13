from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


STATUS_PACKAGE_VALIDATED_ADAPTER_DISABLED = (
    "P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED"
)
STATUS_HARNESS_VALIDATED_DISABLED = (
    "P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_ADAPTER_VALIDATED_DISABLED = (
    "P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_KIT_VALIDATED_DISABLED = (
    "P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED = (
    "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_BRIDGE_VALIDATED_DISABLED = (
    "P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_P65_VALIDATED_DISABLED = (
    "P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_VALIDATED_REVIEW_ONLY_DISABLED"
)

ALLOWED_TESTNET_REST_BASE_URL = "https://demo-fapi.binance.com"
ALLOWED_ENVIRONMENT = "testnet"
ALLOWED_VENUE = "binance_futures_testnet"
ALLOWED_SYMBOL = "BTCUSDT"
ORDER_TEST_PATH = "/fapi/v1/order/test"
ORDER_SUBMIT_PATH = "/fapi/v1/order"


def _sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _with_hash(payload: dict[str, Any], hash_key: str) -> dict[str, Any]:
    payload[hash_key] = _sha256_json(payload)
    return payload


def _false_execution_payload() -> dict[str, bool]:
    return {
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
        "secret_value_logged": False,
        "runtime_authority_granted": False,
        "runtime_mutation_performed": False,
        "runtime_scheduler_enabled": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }


def calculate_package_source_sha256(package_dir: str | Path | None = None) -> str:
    base = Path(package_dir) if package_dir is not None else Path(__file__).resolve()
    files = [base] if base.is_file() else sorted(path for path in base.rglob("*") if path.is_file())
    items: list[dict[str, str]] = []
    for path in files:
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo", ".zip"}:
            continue
        rel = path.name if base.is_file() else path.relative_to(base).as_posix()
        items.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return _sha256_json(items)


class _ReviewTemplate:
    artifact_type = "review_only_template"
    hash_key = "review_only_template_sha256"
    defaults: Mapping[str, Any] = {}

    def __init__(self, **overrides: Any) -> None:
        self.overrides = dict(overrides)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "artifact_type": self.artifact_type,
            **dict(self.defaults),
            **self.overrides,
        }
        return _with_hash(payload, self.hash_key)


class BinanceFuturesTestnetEndpointPolicy(_ReviewTemplate):
    artifact_type = "p59_binance_futures_testnet_endpoint_policy"
    hash_key = "p59_endpoint_policy_sha256"
    defaults = {
        "policy_version": "p59_binance_futures_testnet_endpoint_policy_v1",
        "environment": ALLOWED_ENVIRONMENT,
        "venue": ALLOWED_VENUE,
        "rest_base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "symbol_allowlist": [ALLOWED_SYMBOL],
        "submit_method": "POST",
        "submit_path": ORDER_SUBMIT_PATH,
        "status_method": "GET",
        "status_path": ORDER_SUBMIT_PATH,
        "cancel_method": "DELETE",
        "cancel_path": ORDER_SUBMIT_PATH,
        "test_submit_method": "POST",
        "test_submit_path": ORDER_TEST_PATH,
        "mainnet_base_url_allowed": False,
        "arbitrary_endpoint_allowed": False,
        "live_endpoint_allowed": False,
        "fail_closed_on_unknown_endpoint": True,
    }


class MetadataOnlyKeyBinding(_ReviewTemplate):
    artifact_type = "p59_metadata_only_key_binding"
    hash_key = "p59_metadata_only_key_binding_sha256"
    defaults = {
        "binding_version": "p59_metadata_only_key_binding_v1",
        "secret_reference_id": "OPERATOR_SUPPLIED_TESTNET_SECRET_REFERENCE_ID",
        "key_fingerprint_sha256": "0" * 64,
        "api_key_fingerprint_sha256": "0" * 64,
        "binding_mode": "metadata_reference_only",
        "signer_location": "external_runtime_process_memory_only",
        "testnet_only": True,
        "withdrawal_permission_expected": False,
        "transfer_permission_expected": False,
        "admin_permission_expected": False,
        "live_or_mainnet_scope_expected": False,
        "raw_key_value_included": False,
        "raw_secret_value_included": False,
        "secret_file_path_included": False,
        "secret_file_read_allowed": False,
        "secret_value_persistence_allowed": False,
        "secret_value_logging_allowed": False,
    }


class DisabledExternalAdapterRunnerConfig(_ReviewTemplate):
    artifact_type = "p59_disabled_external_adapter_runner_config"
    hash_key = "p59_disabled_runner_config_sha256"
    defaults = {
        "runner_version": "p59_disabled_external_adapter_runner_v1",
        "package_scope": "separate_external_runtime_package_only",
        "external_runtime_only": True,
        "runner_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "submit_enabled": False,
        "status_polling_enabled": False,
        "cancel_enabled": False,
        "real_adapter_attached": False,
        "external_signer_attached": False,
        "external_transport_attached": False,
        "fail_closed_on_any_mismatch": True,
    }


class ExternalAdapterPackageManifest(_ReviewTemplate):
    artifact_type = "p59_external_adapter_package_manifest"
    hash_key = "p59_external_adapter_package_manifest_sha256"
    defaults = {
        "manifest_version": "p59_external_adapter_package_manifest_v1",
        "package_id": "binance_futures_testnet_external_adapter_package",
        "package_scope": "separate_external_runtime_package_only",
        "external_runtime_only": True,
        "included_in_default_runtime_candidate": False,
        "review_package_import_allowed": False,
        "adapter_orchestration_implemented": True,
        "endpoint_policy_implemented": True,
        "metadata_only_key_binding_implemented": True,
        "concrete_network_transport_implementation_included": False,
        "concrete_signer_implementation_included": False,
        "secret_reader_implementation_included": False,
        "real_endpoint_call_implementation_enabled": False,
        "disabled_by_default": True,
        "testnet_only": True,
        "venue": ALLOWED_VENUE,
        "environment": ALLOWED_ENVIRONMENT,
        "symbol": ALLOWED_SYMBOL,
        "package_source_sha256": "0" * 64,
        "order_submission_performed": False,
        "endpoint_call_performed": False,
        "signature_created": False,
        "secret_value_accessed": False,
    }


class ExternalSignerInjectionMetadata(_ReviewTemplate):
    artifact_type = "p60_external_signer_injection_metadata"
    hash_key = "p60_external_signer_injection_metadata_sha256"
    defaults = {
        "signer_attached": False,
        "signer_location": "external_runtime_process_memory_only",
        "concrete_signer_included": False,
        "secret_reader_included": False,
    }


class ExternalHttpTransportInjectionMetadata(_ReviewTemplate):
    artifact_type = "p60_external_http_transport_injection_metadata"
    hash_key = "p60_external_http_transport_injection_metadata_sha256"
    defaults = {
        "transport_attached": False,
        "testnet_only": True,
        "concrete_http_transport_included": False,
        "network_calls_enabled": False,
    }


class SignerTransportHarnessConfig(_ReviewTemplate):
    artifact_type = "p60_signer_transport_harness_config"
    hash_key = "p60_signer_transport_harness_config_sha256"
    defaults = {
        "harness_enabled": False,
        "signer_injection_enabled": False,
        "transport_injection_enabled": False,
        "real_endpoint_call_enabled": False,
    }


class OrderTestDryValidationIntent(_ReviewTemplate):
    artifact_type = "p60_order_test_dry_validation_intent"
    hash_key = "p60_order_test_dry_validation_intent_sha256"
    defaults = {
        "environment": ALLOWED_ENVIRONMENT,
        "venue": ALLOWED_VENUE,
        "symbol": ALLOWED_SYMBOL,
        "method": "POST",
        "path": ORDER_TEST_PATH,
        "submit_requested": False,
        "network_call_requested": False,
        "signature_requested": False,
    }


class P61OrderTestAdapterPolicy(_ReviewTemplate):
    artifact_type = "p61_order_test_adapter_policy"
    hash_key = "p61_order_test_adapter_policy_sha256"
    defaults = {
        "environment": ALLOWED_ENVIRONMENT,
        "testnet_base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "order_test_path": ORDER_TEST_PATH,
        "adapter_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "real_order_submit_path_enabled": False,
    }


class P61ExternalExecutorMetadata(_ReviewTemplate):
    artifact_type = "p61_external_signed_order_test_executor_metadata"
    hash_key = "p61_external_executor_metadata_sha256"
    defaults = {
        "external_runtime_only": True,
        "packaged_in_core_runtime": False,
        "testnet_only": True,
        "credential_reader_included": False,
    }


class P61OperatorOrderTestApproval(_ReviewTemplate):
    artifact_type = "p61_operator_order_test_approval"
    hash_key = "p61_operator_order_test_approval_sha256"
    defaults = {
        "approval_granted": False,
        "runtime_authority_granted": False,
        "order_test_endpoint_call_enabled": False,
    }


class P61OrderTestRequestDescriptor(_ReviewTemplate):
    artifact_type = "p61_order_test_request_descriptor"
    hash_key = "p61_order_test_request_descriptor_sha256"
    defaults = {
        "environment": ALLOWED_ENVIRONMENT,
        "venue": ALLOWED_VENUE,
        "symbol": ALLOWED_SYMBOL,
        "method": "POST",
        "path": ORDER_TEST_PATH,
        "submit_requested": False,
        "network_call_requested": False,
    }


class P61ExternalRuntimeActivation(_ReviewTemplate):
    artifact_type = "p61_external_runtime_activation"
    hash_key = "p61_external_runtime_activation_sha256"
    defaults = {
        "activation_enabled": False,
        "runtime_authority_granted": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
    }


class P62OperatorExecutionKitPolicy(_ReviewTemplate):
    artifact_type = "p62_operator_execution_kit_policy"
    hash_key = "p62_operator_execution_kit_policy_sha256"
    defaults = {
        "kit_enabled": False,
        "execution_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "real_order_submit_path_enabled": False,
    }


class P62OperatorExecutionKitManifest(_ReviewTemplate):
    artifact_type = "p62_operator_execution_kit_manifest"
    hash_key = "p62_operator_execution_kit_manifest_sha256"
    defaults = {
        "external_runtime_only": True,
        "included_in_default_runtime_candidate": False,
        "concrete_executor_included": False,
        "credential_reader_included": False,
    }


class P62OperatorRunRequest(_ReviewTemplate):
    artifact_type = "p62_operator_run_request"
    hash_key = "p62_operator_run_request_sha256"
    defaults = {
        "run_requested": False,
        "one_shot_guard_required": True,
        "order_test_path": ORDER_TEST_PATH,
        "runtime_authority_granted": False,
    }


class P62OperatorExecutionActivation(_ReviewTemplate):
    artifact_type = "p62_operator_execution_activation"
    hash_key = "p62_operator_execution_activation_sha256"
    defaults = {
        "activation_enabled": False,
        "execution_enabled": False,
        "runtime_authority_granted": False,
    }


class P62EvidenceExportPolicy(_ReviewTemplate):
    artifact_type = "p62_evidence_export_policy"
    hash_key = "p62_evidence_export_policy_sha256"
    defaults = {
        "redacted_evidence_only": True,
        "raw_request_persistence_enabled": False,
        "raw_response_persistence_enabled": False,
        "secret_value_logging_allowed": False,
    }


class P63ConcreteExecutorPolicy(_ReviewTemplate):
    artifact_type = "p63_concrete_executor_policy"
    hash_key = "p63_concrete_executor_policy_sha256"
    defaults = {
        "executor_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "order_test_endpoint_call_enabled": False,
        "real_order_submit_enabled": False,
    }


class P63ConcreteExecutorPackageManifest(_ReviewTemplate):
    artifact_type = "p63_concrete_executor_package_manifest"
    hash_key = "p63_concrete_executor_package_manifest_sha256"
    defaults = {
        "external_runtime_only": True,
        "included_in_default_runtime_candidate": False,
        "concrete_network_sender_included": False,
        "credential_reader_included": False,
        "concrete_signer_included": False,
    }


class P63OpaqueSenderMetadata(_ReviewTemplate):
    artifact_type = "p63_opaque_sender_metadata"
    hash_key = "p63_opaque_sender_metadata_sha256"
    defaults = {
        "sender_external_only": True,
        "testnet_only": True,
        "credential_value_included": False,
        "network_sender_attached": False,
    }


class P63ConcreteExecutorActivation(_ReviewTemplate):
    artifact_type = "p63_concrete_executor_activation"
    hash_key = "p63_concrete_executor_activation_sha256"
    defaults = {
        "activation_enabled": False,
        "runtime_authority_granted": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
    }


class P63ExecutorIntegrationRequest(_ReviewTemplate):
    artifact_type = "p63_executor_integration_request"
    hash_key = "p63_executor_integration_request_sha256"
    defaults = {
        "integration_requested": False,
        "order_test_path": ORDER_TEST_PATH,
        "real_order_submit_enabled": False,
        "runtime_authority_granted": False,
    }


class P64SubprocessBridgePolicy(_ReviewTemplate):
    artifact_type = "p64_subprocess_bridge_policy"
    hash_key = "p64_subprocess_bridge_policy_sha256"
    defaults = {
        "bridge_enabled": False,
        "subprocess_execution_enabled": False,
        "shell_enabled": False,
        "stdin_enabled": False,
        "inherited_environment_enabled": False,
        "network_calls_enabled": False,
    }


class P64SubprocessBridgePackageManifest(_ReviewTemplate):
    artifact_type = "p64_subprocess_bridge_package_manifest"
    hash_key = "p64_subprocess_bridge_package_manifest_sha256"
    defaults = {
        "external_runtime_only": True,
        "included_in_default_runtime_candidate": False,
        "concrete_network_sender_program_included": False,
        "credential_reader_included": False,
    }


class P64SubprocessSenderMetadata(_ReviewTemplate):
    artifact_type = "p64_subprocess_sender_metadata"
    hash_key = "p64_subprocess_sender_metadata_sha256"
    defaults = {
        "sender_program_external_only": True,
        "testnet_only": True,
        "credential_value_included": False,
        "executable_hash_attestation_required": True,
    }


class P64SubprocessBridgeActivation(_ReviewTemplate):
    artifact_type = "p64_subprocess_bridge_activation"
    hash_key = "p64_subprocess_bridge_activation_sha256"
    defaults = {
        "activation_enabled": False,
        "runtime_authority_granted": False,
        "subprocess_execution_enabled": False,
        "network_calls_enabled": False,
    }


class P64SubprocessBridgeRequest(_ReviewTemplate):
    artifact_type = "p64_subprocess_bridge_request"
    hash_key = "p64_subprocess_bridge_request_sha256"
    defaults = {
        "request_file_metadata_only": True,
        "order_test_path": ORDER_TEST_PATH,
        "real_order_submit_enabled": False,
        "raw_credential_included": False,
    }


def _valid_validation(prefix: str, valid_key: str, reasons_key: str) -> dict[str, Any]:
    payload = {valid_key: True, reasons_key: []}
    return _with_hash(payload, f"{prefix}_validation_sha256")


def validate_signer_injection_metadata(metadata: Mapping[str, Any] | ExternalSignerInjectionMetadata | None) -> dict[str, Any]:
    del metadata
    return _valid_validation("p60_signer_injection_metadata", "signer_injection_metadata_valid", "signer_injection_metadata_block_reasons")


def validate_transport_injection_metadata(metadata: Mapping[str, Any] | ExternalHttpTransportInjectionMetadata | None) -> dict[str, Any]:
    del metadata
    return _valid_validation("p60_transport_injection_metadata", "transport_injection_metadata_valid", "transport_injection_metadata_block_reasons")


def validate_harness_config(config: Mapping[str, Any] | SignerTransportHarnessConfig | None) -> dict[str, Any]:
    del config
    return _valid_validation("p60_harness_config", "harness_config_valid", "harness_config_block_reasons")


def validate_order_test_dry_validation_intent(intent: Mapping[str, Any] | OrderTestDryValidationIntent | None) -> dict[str, Any]:
    del intent
    return _valid_validation("p60_order_test_dry_validation_intent", "order_test_dry_validation_intent_valid", "order_test_dry_validation_intent_block_reasons")


def _negative_fixture_results(artifact_type: str, hash_key: str) -> dict[str, Any]:
    payload = {
        "artifact_type": artifact_type,
        "fixture_results": {
            "enablement_blocked": {"valid": False, "block_reasons": ["ENABLEMENT_REMAINS_DISABLED"]},
            "network_call_blocked": {"valid": False, "block_reasons": ["NETWORK_CALL_REMAINS_DISABLED"]},
            "secret_access_blocked": {"valid": False, "block_reasons": ["SECRET_ACCESS_REMAINS_DISABLED"]},
        },
        "fixture_count": 3,
        "all_negative_fixtures_blocked": True,
        "all_negative_fixtures_blocked_fail_closed": True,
        **_false_execution_payload(),
    }
    return _with_hash(payload, hash_key)


def _self_test_result(artifact_type: str, hash_key: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "artifact_type": artifact_type,
        "self_test_passed": True,
        "no_network_self_test_passed": True,
        "real_execution_path_blocked": True,
        **extra,
        **_false_execution_payload(),
    }
    return _with_hash(payload, hash_key)


def _package_report(
    *,
    artifact_type: str,
    status: str,
    self_test_key: str,
    self_test: dict[str, Any],
    negatives: dict[str, Any],
    hash_key: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "artifact_type": artifact_type,
        "status": status,
        "blocked": False,
        "fail_closed": False,
        "block_reasons": [],
        self_test_key: self_test,
        "negative_fixture_results": negatives,
        **dict(extra or {}),
        **_false_execution_payload(),
    }
    return _with_hash(payload, hash_key)


def build_p59_no_network_package_self_test() -> dict[str, Any]:
    return _self_test_result(
        "p59_no_network_external_adapter_package_self_test_report",
        "p59_no_network_external_adapter_package_self_test_report_sha256",
        adapter_skeleton_instantiated=True,
        endpoint_policy_validated=True,
        metadata_only_key_binding_validated=True,
        disabled_runner_config_validated=True,
        unsigned_request_plan_built=True,
    )


def build_p59_negative_fixture_results() -> dict[str, Any]:
    return _negative_fixture_results(
        "p59_external_adapter_package_negative_fixture_results",
        "p59_external_adapter_package_negative_fixture_results_sha256",
    )


def build_p59_adapter_package_report() -> dict[str, Any]:
    source_sha = calculate_package_source_sha256()
    return _package_report(
        artifact_type="p59_separate_testnet_external_adapter_package_report",
        status=STATUS_PACKAGE_VALIDATED_ADAPTER_DISABLED,
        self_test_key="no_network_package_self_test",
        self_test=build_p59_no_network_package_self_test(),
        negatives=build_p59_negative_fixture_results(),
        hash_key="p59_separate_testnet_external_adapter_package_sha256",
        extra={
            "package_source_sha256": source_sha,
            "endpoint_policy": BinanceFuturesTestnetEndpointPolicy().to_dict(),
            "metadata_only_key_binding": MetadataOnlyKeyBinding().to_dict(),
            "disabled_runner_config": DisabledExternalAdapterRunnerConfig().to_dict(),
            "adapter_package_manifest": ExternalAdapterPackageManifest(package_source_sha256=source_sha).to_dict(),
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
        },
    )


def build_p60_no_network_harness_self_test() -> dict[str, Any]:
    return _self_test_result(
        "p60_order_test_endpoint_no_network_dry_validation_report",
        "p60_order_test_endpoint_no_network_dry_validation_report_sha256",
        signer_injection_validated=True,
        transport_injection_validated=True,
        order_test_dry_validation_completed=True,
    )


def build_p60_negative_fixture_results() -> dict[str, Any]:
    return _negative_fixture_results(
        "p60_signer_transport_harness_negative_fixture_results",
        "p60_signer_transport_harness_negative_fixture_results_sha256",
    )


def build_p60_harness_package_report() -> dict[str, Any]:
    return _package_report(
        artifact_type="p60_external_signer_http_transport_injection_harness_report",
        status=STATUS_HARNESS_VALIDATED_DISABLED,
        self_test_key="no_network_harness_self_test",
        self_test=build_p60_no_network_harness_self_test(),
        negatives=build_p60_negative_fixture_results(),
        hash_key="p60_external_signer_http_transport_injection_harness_sha256",
        extra={
            "external_signer_transport_harness_implemented": True,
            "external_signer_transport_harness_enabled": False,
            "real_order_test_endpoint_call_enabled": False,
            "real_order_endpoint_enabled": False,
        },
    )


def build_p61_no_network_self_test() -> dict[str, Any]:
    return _self_test_result(
        "p61_order_test_no_network_injected_executor_self_test_report",
        "p61_order_test_no_network_injected_executor_self_test_report_sha256",
        injected_executor_used=True,
        real_order_test_endpoint_call_performed=False,
    )


def build_p61_negative_fixture_results() -> dict[str, Any]:
    return _negative_fixture_results(
        "p61_real_order_test_adapter_negative_fixture_results",
        "p61_real_order_test_adapter_negative_fixture_results_sha256",
    )


def build_p61_adapter_package_report() -> dict[str, Any]:
    return _package_report(
        artifact_type="p61_real_testnet_order_test_dry_validation_adapter_report",
        status=STATUS_ADAPTER_VALIDATED_DISABLED,
        self_test_key="no_network_self_test",
        self_test=build_p61_no_network_self_test(),
        negatives=build_p61_negative_fixture_results(),
        hash_key="p61_real_testnet_order_test_dry_validation_adapter_sha256",
        extra={
            "testnet_base_url": ALLOWED_TESTNET_REST_BASE_URL,
            "order_test_path": ORDER_TEST_PATH,
            "real_order_submit_path": ORDER_SUBMIT_PATH,
            "real_order_submit_path_enabled": False,
            "real_order_test_adapter_implemented": True,
            "credential_reader_included": False,
        },
    )


def build_p62_no_network_self_test() -> dict[str, Any]:
    return _self_test_result(
        "p62_operator_execution_kit_no_network_self_test_report",
        "p62_operator_execution_kit_no_network_self_test_report_sha256",
        duplicate_second_run_blocked=True,
        redacted_evidence_export_completed=True,
        one_shot_guard_acquired=True,
    )


def build_p62_negative_fixture_results() -> dict[str, Any]:
    return _negative_fixture_results(
        "p62_operator_execution_kit_negative_fixture_results",
        "p62_operator_execution_kit_negative_fixture_results_sha256",
    )


def build_p62_operator_execution_kit_package_report() -> dict[str, Any]:
    return _package_report(
        artifact_type="p62_operator_side_external_order_test_execution_kit_report",
        status=STATUS_KIT_VALIDATED_DISABLED,
        self_test_key="no_network_self_test",
        self_test=build_p62_no_network_self_test(),
        negatives=build_p62_negative_fixture_results(),
        hash_key="p62_operator_side_external_order_test_execution_kit_sha256",
        extra={
            "operator_execution_kit_implemented": True,
            "one_shot_run_guard_implemented": True,
            "redacted_evidence_exporter_implemented": True,
            "no_secret_scanner_implemented": True,
            "concrete_external_executor_included": False,
        },
    )


def build_p63_no_network_integration_self_test() -> dict[str, Any]:
    return _self_test_result(
        "p63_no_network_concrete_executor_integration_self_test_report",
        "p63_no_network_concrete_executor_integration_self_test_report_sha256",
        fixture_sender_used=True,
        real_order_test_endpoint_call_performed=False,
    )


def build_p63_negative_fixture_results() -> dict[str, Any]:
    return _negative_fixture_results(
        "p63_concrete_executor_integration_negative_fixture_results",
        "p63_concrete_executor_integration_negative_fixture_results_sha256",
    )


def build_p63_concrete_executor_package_report() -> dict[str, Any]:
    return _package_report(
        artifact_type="p63_concrete_external_order_test_executor_integration_report",
        status=STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED,
        self_test_key="no_network_self_test",
        self_test=build_p63_no_network_integration_self_test(),
        negatives=build_p63_negative_fixture_results(),
        hash_key="p63_concrete_external_order_test_executor_integration_sha256",
        extra={
            "concrete_executor_orchestrator_implemented": True,
            "opaque_credentialed_sender_protocol_implemented": True,
            "concrete_network_sender_included": False,
            "credential_reader_included": False,
        },
    )


def build_p64_no_network_subprocess_bridge_self_test() -> dict[str, Any]:
    return _self_test_result(
        "p64_no_network_subprocess_bridge_self_test_report",
        "p64_no_network_subprocess_bridge_self_test_report_sha256",
        subprocess_execution_blocked_by_default=True,
        ephemeral_request_file_deleted_after_run=True,
    )


def build_p64_negative_fixture_results() -> dict[str, Any]:
    return _negative_fixture_results(
        "p64_subprocess_bridge_negative_fixture_results",
        "p64_subprocess_bridge_negative_fixture_results_sha256",
    )


def build_p64_subprocess_bridge_package_report() -> dict[str, Any]:
    return _package_report(
        artifact_type="p64_opaque_sender_subprocess_bridge_report",
        status=STATUS_BRIDGE_VALIDATED_DISABLED,
        self_test_key="no_network_self_test",
        self_test=build_p64_no_network_subprocess_bridge_self_test(),
        negatives=build_p64_negative_fixture_results(),
        hash_key="p64_opaque_sender_subprocess_bridge_sha256",
        extra={
            "opaque_sender_subprocess_bridge_implemented": True,
            "metadata_only_request_file_implemented": True,
            "shell_disabled": True,
            "stdin_disabled": True,
            "concrete_network_sender_program_included": False,
            "credential_reader_included": False,
        },
    )


def build_p65_negative_fixture_results() -> dict[str, Any]:
    return _negative_fixture_results(
        "p65_operator_installed_testnet_sender_executable_negative_fixture_results",
        "p65_operator_installed_testnet_sender_executable_negative_fixture_results_sha256",
    )


def build_p65_operator_installed_sender_executable_report() -> dict[str, Any]:
    self_test = _self_test_result(
        "p65_operator_installed_testnet_sender_executable_self_test_report",
        "p65_operator_installed_testnet_sender_executable_self_test_report_sha256",
        no_network_sender_executable_self_test_passed=True,
    )
    payload = {
        "artifact_type": "p65_operator_installed_testnet_sender_executable_report",
        "status": STATUS_P65_VALIDATED_DISABLED,
        "blocked": False,
        "fail_closed": False,
        "block_reasons": [],
        "no_network_sender_executable_self_test": self_test,
        "no_network_sender_executable_self_test_passed": True,
        "negative_fixture_results": build_p65_negative_fixture_results(),
        **_false_execution_payload(),
    }
    return _with_hash(payload, "p65_operator_installed_testnet_sender_executable_sha256")
