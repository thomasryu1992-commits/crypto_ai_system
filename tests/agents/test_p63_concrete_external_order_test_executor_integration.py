from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.concrete_external_order_test_executor_integration import (
    STATUS_VALIDATED_REVIEW_ONLY_DISABLED,
    persist_p63_concrete_external_order_test_executor_integration,
    validate_p62_source,
)
from external_runtime_packages.binance_futures_testnet_adapter import (
    EXACT_P63_OPERATOR_EXECUTOR_PHRASE,
    P63_APPROVED_EXTERNAL_RUNTIME_SCOPE,
    P63_NO_NETWORK_SELF_TEST_SCOPE,
    AdapterPackageDisabledError,
    AdapterPackageValidationError,
    MetadataOnlyKeyBinding,
    P61OrderTestRequestDescriptor,
    P63ConcreteExecutorActivation,
    P63ConcreteExecutorPackageManifest,
    P63ConcreteExecutorPolicy,
    P63ConcreteExternalOrderTestExecutor,
    P63ExecutorIntegrationRequest,
    P63NoNetworkOpaqueCredentialedSender,
    P63OpaqueSenderMetadata,
    STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED,
    build_p63_concrete_executor_package_report,
    build_p63_negative_fixture_results,
    build_p63_no_network_integration_self_test,
    validate_concrete_executor_activation,
    validate_concrete_executor_manifest,
    validate_concrete_executor_policy,
    validate_executor_integration_request,
    validate_opaque_sender_metadata,
)


def _write_min_project(root: Path) -> None:
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n"
        "  name: tmp-crypto-ai-system\n"
        "  version: test\n"
        "storage:\n"
        "  latest_dir: storage/latest\n"
        "  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname='tmp'\nversion='0.1.0'\n", encoding="utf-8"
    )


def _write_p62_ready(root: Path) -> None:
    payload = {
        "artifact_type": "p62_operator_side_external_order_test_execution_kit_report",
        "status": "P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_VALIDATED_REVIEW_ONLY_DISABLED",
        "blocked": False,
        "operator_execution_kit_implemented": True,
        "one_shot_run_guard_implemented": True,
        "redacted_evidence_exporter_implemented": True,
        "no_secret_scanner_implemented": True,
        "p58_bridge_exporter_implemented": True,
        "external_executor_injection_contract_implemented": True,
        "no_network_operator_kit_self_test_passed": True,
        "one_shot_duplicate_run_blocked_in_self_test": True,
        "redacted_evidence_export_self_test_passed": True,
        "negative_fixtures_all_blocked": True,
        "testnet_base_url": "https://demo-fapi.binance.com",
        "order_test_path": "/fapi/v1/order/test",
        "concrete_external_executor_included": False,
        "credential_reader_included": False,
        "secret_file_reader_included": False,
        "secret_file_writer_included": False,
        "operator_side_external_order_test_execution_kit_enabled": False,
        "operator_side_external_order_test_execution_enabled": False,
        "operator_side_external_order_test_network_calls_enabled": False,
        "operator_side_external_order_test_signing_enabled": False,
        "operator_side_external_order_test_endpoint_call_enabled": False,
        "operator_side_external_order_test_endpoint_call_performed": False,
        "operator_side_external_order_test_real_evidence_exported": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_enabled": False,
        "real_order_endpoint_called": False,
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        "actual_order_submission_performed": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "runtime_mutation_performed": False,
        "p62_operator_side_external_order_test_execution_kit_sha256": "a" * 64,
    }
    atomic_write_json(
        root
        / "storage"
        / "latest"
        / "p62_operator_side_external_order_test_execution_kit_report.json",
        payload,
    )


def _fixture_activation(request_sha: str) -> dict[str, object]:
    return P63ConcreteExecutorActivation(
        activation_scope=P63_NO_NETWORK_SELF_TEST_SCOPE,
        exact_operator_phrase=EXACT_P63_OPERATOR_EXECUTOR_PHRASE,
        operator_confirmation_sha256="1" * 64,
        source_p62_report_sha256="2" * 64,
        p62_run_request_sha256="3" * 64,
        p61_request_descriptor_sha256=request_sha,
        one_shot_nonce_sha256="4" * 64,
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


def test_p63_policy_defaults_are_testnet_order_test_only_and_disabled() -> None:
    policy = P63ConcreteExecutorPolicy().to_dict()
    validation = validate_concrete_executor_policy(policy)
    assert validation["concrete_executor_policy_valid"] is True
    assert policy["base_url"] == "https://demo-fapi.binance.com"
    assert policy["path"] == "/fapi/v1/order/test"
    assert policy["executor_enabled"] is False
    assert policy["real_order_submit_enabled"] is False


def test_p63_policy_blocks_enablement_and_raw_persistence() -> None:
    policy = replace(
        P63ConcreteExecutorPolicy(),
        executor_enabled=True,
        network_calls_enabled=True,
        raw_response_persistence_allowed=True,
    ).to_dict()
    validation = validate_concrete_executor_policy(policy)
    assert validation["concrete_executor_policy_valid"] is False
    reasons = validation["concrete_executor_policy_block_reasons"]
    assert "P63_POLICY_EXECUTOR_ENABLED_NOT_FALSE" in reasons
    assert "P63_POLICY_NETWORK_CALLS_ENABLED_NOT_FALSE" in reasons
    assert "P63_POLICY_RAW_RESPONSE_PERSISTENCE_ALLOWED_NOT_FALSE" in reasons


def test_p63_manifest_is_external_and_excluded_from_default_runtime() -> None:
    manifest = P63ConcreteExecutorPackageManifest().to_dict()
    validation = validate_concrete_executor_manifest(manifest)
    assert validation["concrete_executor_manifest_valid"] is True
    assert manifest["concrete_executor_orchestrator_implemented"] is True
    assert manifest["included_in_default_runtime_candidate"] is False
    assert manifest["concrete_network_sender_included"] is False


def test_p63_manifest_blocks_runtime_candidate_and_network_sender() -> None:
    manifest = replace(
        P63ConcreteExecutorPackageManifest(),
        included_in_default_runtime_candidate=True,
        concrete_network_sender_included=True,
    ).to_dict()
    validation = validate_concrete_executor_manifest(manifest)
    assert validation["concrete_executor_manifest_valid"] is False
    reasons = validation["concrete_executor_manifest_block_reasons"]
    assert "P63_MANIFEST_INCLUDED_IN_DEFAULT_RUNTIME_CANDIDATE_NOT_FALSE" in reasons
    assert "P63_MANIFEST_CONCRETE_NETWORK_SENDER_INCLUDED_NOT_FALSE" in reasons


def test_p63_sender_metadata_is_testnet_opaque_and_external_only() -> None:
    metadata = P63OpaqueSenderMetadata().to_dict()
    validation = validate_opaque_sender_metadata(metadata)
    assert validation["opaque_sender_metadata_valid"] is True
    assert metadata["base_url"] == "https://demo-fapi.binance.com"
    assert metadata["raw_credential_exposed_to_executor"] is False
    assert metadata["included_in_review_package"] is False


def test_p63_sender_metadata_blocks_mainnet_and_credential_exposure() -> None:
    metadata = replace(
        P63OpaqueSenderMetadata(),
        base_url="https://fapi.binance.com",
        raw_credential_exposed_to_executor=True,
    ).to_dict()
    validation = validate_opaque_sender_metadata(metadata)
    assert validation["opaque_sender_metadata_valid"] is False
    reasons = validation["opaque_sender_metadata_block_reasons"]
    assert "P63_SENDER_BASE_URL_INVALID" in reasons
    assert "P63_SENDER_RAW_CREDENTIAL_EXPOSED_TO_EXECUTOR_NOT_FALSE" in reasons


def test_p63_activation_and_request_templates_are_disabled() -> None:
    activation = P63ConcreteExecutorActivation().to_dict()
    request = P63ExecutorIntegrationRequest().to_dict()
    assert validate_concrete_executor_activation(
        activation, require_enabled=False, allow_fixture=True
    )["concrete_executor_activation_valid"] is True
    assert validate_executor_integration_request(
        request, require_requested=False, allow_fixture=True
    )["executor_integration_request_valid"] is True
    assert activation["executor_enabled"] is False
    assert request["integration_requested"] is False


def test_p63_fixture_activation_validates_for_no_network_self_test() -> None:
    request = P61OrderTestRequestDescriptor().to_dict()
    activation = _fixture_activation(request["p61_order_test_request_descriptor_sha256"])
    validation = validate_concrete_executor_activation(
        activation, require_enabled=True, allow_fixture=True
    )
    assert validation["concrete_executor_activation_valid"] is True
    assert validation["fixture_only"] is True


def test_p63_concrete_executor_runs_only_with_fixture_sender_in_self_test() -> None:
    request = P61OrderTestRequestDescriptor().to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256="5" * 64,
        api_key_fingerprint_sha256="6" * 64,
    )
    executor = P63ConcreteExternalOrderTestExecutor(
        activation=_fixture_activation(request["p61_order_test_request_descriptor_sha256"]),
        sender=P63NoNetworkOpaqueCredentialedSender(),
        key_binding=key_binding,
    )
    result = executor.execute_signed_order_test(
        request_descriptor=request,
        credential_reference_id=key_binding.secret_reference_id,
    )
    assert result["fixture_executor_used"] is True
    assert result["http_request_sent"] is False
    assert result["signature_created_in_external_process"] is False
    assert result["actual_order_submission_performed"] is False


def test_p63_real_scope_rejects_fixture_sender_and_submit_is_disabled() -> None:
    request = replace(
        P61OrderTestRequestDescriptor(),
        execution_scope="p61_approved_external_runtime_order_test_only",
        fixture_only=False,
        real_order_test_requested=True,
    ).to_dict()
    activation = P63ConcreteExecutorActivation(
        activation_scope=P63_APPROVED_EXTERNAL_RUNTIME_SCOPE,
        exact_operator_phrase=EXACT_P63_OPERATOR_EXECUTOR_PHRASE,
        operator_confirmation_sha256="1" * 64,
        source_p62_report_sha256="2" * 64,
        p62_run_request_sha256="3" * 64,
        p61_request_descriptor_sha256=request["p61_order_test_request_descriptor_sha256"],
        one_shot_nonce_sha256="4" * 64,
        executor_enabled=True,
        opaque_sender_injection_enabled=True,
        network_calls_enabled=True,
        signing_enabled=True,
        order_test_call_enabled=True,
        evidence_export_enabled=True,
        no_secret_scan_enabled=True,
        separate_operator_approval_validated=True,
        one_shot_guard_validated=True,
        fixture_only=False,
    ).to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256="5" * 64,
        api_key_fingerprint_sha256="6" * 64,
    )
    executor = P63ConcreteExternalOrderTestExecutor(
        activation=activation,
        sender=P63NoNetworkOpaqueCredentialedSender(),
        key_binding=key_binding,
    )
    with pytest.raises(AdapterPackageValidationError):
        executor.execute_signed_order_test(
            request_descriptor=request,
            credential_reference_id=key_binding.secret_reference_id,
        )
    with pytest.raises(AdapterPackageDisabledError):
        executor.execute_real_order_submit()


def test_p63_no_network_integration_self_test_passes() -> None:
    report = build_p63_no_network_integration_self_test()
    assert report["self_test_passed"] is True
    assert report["concrete_executor_orchestrator_used"] is True
    assert report["opaque_fixture_sender_used"] is True
    assert report["concrete_network_sender_used"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["actual_order_submission_performed"] is False


def test_p63_negative_fixtures_and_package_report_are_safe() -> None:
    negatives = build_p63_negative_fixture_results()
    assert negatives["fixture_count"] == 10
    assert negatives["all_negative_fixtures_blocked_fail_closed"] is True
    report = build_p63_concrete_executor_package_report()
    assert report["status"] == STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED
    assert report["blocked"] is False
    assert report["concrete_executor_orchestrator_implemented"] is True
    assert report["concrete_network_sender_included"] is False
    assert report["http_request_sent"] is False
    assert report["actual_order_submission_performed"] is False


def test_p63_source_validation_and_persist_expected_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_min_project(tmp_path)
    _write_p62_ready(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    source = read_json(
        tmp_path
        / "storage"
        / "latest"
        / "p62_operator_side_external_order_test_execution_kit_report.json"
    )
    assert validate_p62_source(source)["p62_source_valid"] is True
    report = persist_p63_concrete_external_order_test_executor_integration(cfg=cfg)
    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    latest = tmp_path / "storage" / "latest"
    expected = [
        "p63_concrete_external_order_test_executor_integration_report.json",
        "p63_concrete_executor_policy_TEMPLATE_DISABLED.json",
        "p63_concrete_executor_package_manifest.json",
        "p63_opaque_sender_metadata_TEMPLATE_EXTERNAL_ONLY.json",
        "p63_concrete_executor_activation_TEMPLATE_DISABLED.json",
        "p63_executor_integration_request_TEMPLATE_NO_CALL.json",
        "p63_no_network_concrete_executor_integration_self_test_report.json",
        "p63_concrete_executor_integration_negative_fixture_results.json",
        "p63_concrete_external_order_test_executor_integration_summary.json",
        "p63_concrete_external_order_test_executor_integration_registry_record.json",
    ]
    for name in expected:
        assert (latest / name).exists(), name
    saved = read_json(latest / expected[0])
    assert saved["p63_concrete_external_order_test_executor_enabled"] is False
    assert saved["p63_concrete_network_sender_included"] is False
    assert saved["http_request_sent"] is False
    assert saved["signature_created"] is False
    assert saved["secret_value_accessed"] is False
