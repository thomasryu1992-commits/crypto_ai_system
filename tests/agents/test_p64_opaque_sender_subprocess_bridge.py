from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.opaque_sender_subprocess_bridge import (
    STATUS_VALIDATED_REVIEW_ONLY_DISABLED,
    persist_p64_opaque_sender_subprocess_bridge,
    validate_p63_source,
)
from external_runtime_packages.binance_futures_testnet_adapter import (
    P64SubprocessBridgeActivation,
    P64SubprocessBridgePackageManifest,
    P64SubprocessBridgePolicy,
    P64SubprocessBridgeRequest,
    P64SubprocessSenderMetadata,
    STATUS_BRIDGE_VALIDATED_DISABLED,
    build_p64_negative_fixture_results,
    build_p64_no_network_subprocess_bridge_self_test,
    build_p64_subprocess_bridge_package_report,
    validate_subprocess_bridge_activation,
    validate_subprocess_bridge_manifest,
    validate_subprocess_bridge_policy,
    validate_subprocess_bridge_request,
    validate_subprocess_sender_metadata,
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


def _write_p63_ready(root: Path) -> None:
    payload = {
        "artifact_type": "p63_concrete_external_order_test_executor_integration_report",
        "status": "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VALIDATED_REVIEW_ONLY_DISABLED",
        "blocked": False,
        "concrete_executor_orchestrator_implemented": True,
        "opaque_credentialed_sender_protocol_implemented": True,
        "metadata_only_credential_reference_enforced": True,
        "external_process_memory_credential_boundary_enforced": True,
        "p61_request_hash_binding_enforced": True,
        "p62_run_hash_binding_enforced": True,
        "one_shot_guard_binding_enforced": True,
        "redacted_result_contract_enforced": True,
        "no_network_concrete_executor_integration_self_test_passed": True,
        "negative_fixtures_all_blocked": True,
        "testnet_base_url": "https://demo-fapi.binance.com",
        "order_test_path": "/fapi/v1/order/test",
        "concrete_network_sender_included": False,
        "credential_reader_included": False,
        "secret_file_reader_included": False,
        "secret_file_writer_included": False,
        "concrete_signer_included": False,
        "p63_concrete_external_order_test_executor_enabled": False,
        "p63_opaque_credentialed_sender_injection_enabled": False,
        "p63_external_runtime_network_calls_enabled": False,
        "p63_external_runtime_signing_enabled": False,
        "p63_order_test_endpoint_call_enabled": False,
        "p63_order_test_endpoint_call_performed": False,
        "p63_real_order_submit_enabled": False,
        "p63_real_order_endpoint_called": False,
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
        "p63_concrete_external_order_test_executor_integration_sha256": "a" * 64,
    }
    atomic_write_json(
        root
        / "storage"
        / "latest"
        / "p63_concrete_external_order_test_executor_integration_report.json",
        payload,
    )


def test_p64_policy_defaults_are_subprocess_hardened_and_disabled() -> None:
    policy = P64SubprocessBridgePolicy().to_dict()
    validation = validate_subprocess_bridge_policy(policy)
    assert validation["subprocess_bridge_policy_valid"] is True
    assert policy["shell_allowed"] is False
    assert policy["inherited_environment_allowed"] is False
    assert policy["stdin_payload_allowed"] is False
    assert policy["bridge_enabled"] is False


def test_p64_policy_blocks_shell_environment_and_enablement() -> None:
    policy = replace(
        P64SubprocessBridgePolicy(),
        shell_allowed=True,
        inherited_environment_allowed=True,
        bridge_enabled=True,
    ).to_dict()
    validation = validate_subprocess_bridge_policy(policy)
    assert validation["subprocess_bridge_policy_valid"] is False
    reasons = validation["subprocess_bridge_policy_block_reasons"]
    assert "P64_POLICY_SHELL_ALLOWED_NOT_FALSE" in reasons
    assert "P64_POLICY_INHERITED_ENVIRONMENT_ALLOWED_NOT_FALSE" in reasons
    assert "P64_POLICY_BRIDGE_ENABLED_NOT_FALSE" in reasons


def test_p64_manifest_is_external_and_excluded_from_default_runtime() -> None:
    manifest = P64SubprocessBridgePackageManifest().to_dict()
    validation = validate_subprocess_bridge_manifest(manifest)
    assert validation["subprocess_bridge_manifest_valid"] is True
    assert manifest["subprocess_bridge_implemented"] is True
    assert manifest["included_in_default_runtime_candidate"] is False
    assert manifest["concrete_network_sender_program_included"] is False


def test_p64_manifest_blocks_runtime_candidate_and_sender_bundling() -> None:
    manifest = replace(
        P64SubprocessBridgePackageManifest(),
        included_in_default_runtime_candidate=True,
        concrete_network_sender_program_included=True,
    ).to_dict()
    validation = validate_subprocess_bridge_manifest(manifest)
    assert validation["subprocess_bridge_manifest_valid"] is False
    reasons = validation["subprocess_bridge_manifest_block_reasons"]
    assert "P64_MANIFEST_INCLUDED_IN_DEFAULT_RUNTIME_CANDIDATE_NOT_FALSE" in reasons
    assert "P64_MANIFEST_CONCRETE_NETWORK_SENDER_PROGRAM_INCLUDED_NOT_FALSE" in reasons


def test_p64_sender_metadata_template_is_opaque_external_and_testnet_only() -> None:
    metadata = P64SubprocessSenderMetadata().to_dict()
    validation = validate_subprocess_sender_metadata(
        metadata, allow_fixture=False, require_paths=False
    )
    assert validation["subprocess_sender_metadata_valid"] is True
    assert metadata["base_url"] == "https://demo-fapi.binance.com"
    assert metadata["raw_credential_exposed_to_bridge"] is False
    assert metadata["included_in_review_package"] is False


def test_p64_sender_metadata_blocks_mainnet_and_credential_exposure() -> None:
    metadata = replace(
        P64SubprocessSenderMetadata(),
        base_url="https://fapi.binance.com",
        raw_credential_exposed_to_bridge=True,
    ).to_dict()
    validation = validate_subprocess_sender_metadata(
        metadata, allow_fixture=False, require_paths=False
    )
    assert validation["subprocess_sender_metadata_valid"] is False
    reasons = validation["subprocess_sender_metadata_block_reasons"]
    assert "P64_SENDER_BASE_URL_INVALID" in reasons
    assert "P64_SENDER_RAW_CREDENTIAL_EXPOSED_TO_BRIDGE_NOT_FALSE" in reasons


def test_p64_activation_and_request_templates_are_disabled() -> None:
    activation = P64SubprocessBridgeActivation().to_dict()
    request = P64SubprocessBridgeRequest().to_dict()
    assert validate_subprocess_bridge_activation(
        activation, require_enabled=False, allow_fixture=True
    )["subprocess_bridge_activation_valid"] is True
    assert validate_subprocess_bridge_request(
        request, require_requested=False, allow_fixture=True
    )["subprocess_bridge_request_valid"] is True
    assert activation["bridge_enabled"] is False
    assert request["bridge_requested"] is False


def test_p64_activation_blocks_runtime_authority() -> None:
    activation = replace(
        P64SubprocessBridgeActivation(), runtime_authority_granted=True
    ).to_dict()
    validation = validate_subprocess_bridge_activation(
        activation, require_enabled=False, allow_fixture=True
    )
    assert validation["subprocess_bridge_activation_valid"] is False
    assert (
        "P64_ACTIVATION_RUNTIME_AUTHORITY_GRANTED_NOT_FALSE"
        in validation["subprocess_bridge_activation_block_reasons"]
    )


def test_p64_request_blocks_real_submit_and_raw_credential() -> None:
    request = replace(
        P64SubprocessBridgeRequest(),
        real_order_submit_requested=True,
        raw_credential_included=True,
    ).to_dict()
    validation = validate_subprocess_bridge_request(
        request, require_requested=False, allow_fixture=True
    )
    assert validation["subprocess_bridge_request_valid"] is False
    reasons = validation["subprocess_bridge_request_block_reasons"]
    assert "P64_REQUEST_REAL_ORDER_SUBMIT_REQUESTED_NOT_FALSE" in reasons
    assert "P64_REQUEST_RAW_CREDENTIAL_INCLUDED_NOT_FALSE" in reasons


def test_p64_no_network_subprocess_bridge_self_test_passes() -> None:
    report = build_p64_no_network_subprocess_bridge_self_test()
    assert report["self_test_passed"] is True
    assert report["subprocess_bridge_used"] is True
    assert report["shell_used"] is False
    assert report["inherited_environment_used"] is False
    assert report["stdin_used"] is False
    assert report["fixture_sender_program_packaged"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False


def test_p64_negative_fixtures_and_package_report_are_safe() -> None:
    negatives = build_p64_negative_fixture_results()
    assert negatives["fixture_count"] == 10
    assert negatives["all_negative_fixtures_blocked_fail_closed"] is True
    report = build_p64_subprocess_bridge_package_report()
    assert report["status"] == STATUS_BRIDGE_VALIDATED_DISABLED
    assert report["blocked"] is False
    assert report["subprocess_bridge_implemented"] is True
    assert report["concrete_network_sender_program_included"] is False
    assert report["http_request_sent"] is False
    assert report["actual_order_submission_performed"] is False


def test_p64_source_validation_rejects_unsafe_p63() -> None:
    validation = validate_p63_source(
        {
            "status": "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VALIDATED_REVIEW_ONLY_DISABLED",
            "blocked": False,
            "concrete_executor_orchestrator_implemented": True,
            "opaque_credentialed_sender_protocol_implemented": True,
            "metadata_only_credential_reference_enforced": True,
            "external_process_memory_credential_boundary_enforced": True,
            "p61_request_hash_binding_enforced": True,
            "p62_run_hash_binding_enforced": True,
            "one_shot_guard_binding_enforced": True,
            "redacted_result_contract_enforced": True,
            "no_network_concrete_executor_integration_self_test_passed": True,
            "negative_fixtures_all_blocked": True,
            "testnet_base_url": "https://demo-fapi.binance.com",
            "order_test_path": "/fapi/v1/order/test",
            "concrete_network_sender_included": False,
            "credential_reader_included": False,
            "secret_file_reader_included": False,
            "secret_file_writer_included": False,
            "concrete_signer_included": False,
            "p63_concrete_external_order_test_executor_enabled": False,
            "p63_opaque_credentialed_sender_injection_enabled": False,
            "p63_external_runtime_network_calls_enabled": False,
            "p63_external_runtime_signing_enabled": False,
            "p63_order_test_endpoint_call_enabled": False,
            "p63_order_test_endpoint_call_performed": False,
            "p63_real_order_submit_enabled": False,
            "p63_real_order_endpoint_called": False,
            "real_order_test_endpoint_call_enabled": False,
            "real_order_test_endpoint_call_performed": False,
            "real_order_endpoint_enabled": False,
            "real_order_endpoint_called": False,
            "real_signed_testnet_evidence_present": False,
            "actual_p7_import_ready": False,
            "actual_order_submission_performed": False,
            "http_request_sent": True,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "runtime_mutation_performed": False,
        }
    )
    assert validation["p63_source_valid"] is False
    assert "P64_P63_HTTP_REQUEST_SENT_NOT_FALSE" in validation["p63_source_block_reasons"]


def test_p64_source_validation_and_persist_expected_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_min_project(tmp_path)
    _write_p63_ready(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    report = persist_p64_opaque_sender_subprocess_bridge(cfg=cfg)
    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    assert report["blocked"] is False
    assert report["opaque_sender_subprocess_bridge_implemented"] is True
    assert report["concrete_network_sender_program_included"] is False
    assert report["http_request_sent"] is False
    latest = tmp_path / "storage" / "latest"
    for name in (
        "p64_opaque_sender_subprocess_bridge_report.json",
        "p64_subprocess_bridge_policy_TEMPLATE_DISABLED.json",
        "p64_subprocess_bridge_package_manifest.json",
        "p64_subprocess_sender_metadata_TEMPLATE_EXTERNAL_ONLY.json",
        "p64_subprocess_bridge_activation_TEMPLATE_DISABLED.json",
        "p64_subprocess_bridge_request_TEMPLATE_NO_CALL.json",
        "p64_no_network_subprocess_bridge_self_test_report.json",
        "p64_subprocess_bridge_negative_fixture_results.json",
        "p64_opaque_sender_subprocess_bridge_summary.json",
        "p64_opaque_sender_subprocess_bridge_registry_record.json",
    ):
        assert (latest / name).is_file()
    saved = read_json(latest / "p64_opaque_sender_subprocess_bridge_report.json")
    assert saved["status"] == STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    registry = tmp_path / "storage" / "registries" / "p64_opaque_sender_subprocess_bridge_registry.jsonl"
    assert registry.is_file()
