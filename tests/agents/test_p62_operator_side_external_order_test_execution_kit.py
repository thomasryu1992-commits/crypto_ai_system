from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_side_external_order_test_execution_kit import (
    STATUS_VALIDATED_REVIEW_ONLY_DISABLED,
    persist_p62_operator_side_external_order_test_execution_kit,
    validate_p61_source,
)
from external_runtime_packages.binance_futures_testnet_adapter import (
    EXACT_P62_OPERATOR_KIT_PHRASE,
    P62_NO_NETWORK_SELF_TEST_SCOPE,
    AdapterPackageDisabledError,
    AdapterPackageValidationError,
    OperatorSideExternalOrderTestExecutionKit,
    P61ExternalRuntimeActivation,
    P61OperatorOrderTestApproval,
    P61OrderTestRequestDescriptor,
    P62EvidenceExportPolicy,
    P62OneShotRunGuard,
    P62OperatorExecutionActivation,
    P62OperatorExecutionKitManifest,
    P62OperatorExecutionKitPolicy,
    P62OperatorRunRequest,
    STATUS_KIT_VALIDATED_DISABLED,
    build_p62_negative_fixture_results,
    build_p62_no_network_self_test,
    build_p62_operator_execution_kit_package_report,
    validate_evidence_export_policy,
    validate_operator_execution_activation,
    validate_operator_execution_kit_manifest,
    validate_operator_execution_kit_policy,
    validate_operator_run_request,
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


def _write_p61_ready(root: Path) -> None:
    payload = {
        "artifact_type": "p61_real_testnet_order_test_dry_validation_adapter_report",
        "status": "P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_VALIDATED_REVIEW_ONLY_DISABLED",
        "blocked": False,
        "real_order_test_adapter_implemented": True,
        "approved_external_runtime_order_test_path_implemented": True,
        "external_signed_order_test_executor_protocol_implemented": True,
        "metadata_only_credential_reference_enforced": True,
        "external_process_memory_credential_boundary_enforced": True,
        "redacted_response_contract_enforced": True,
        "no_network_injected_executor_self_test_passed": True,
        "negative_fixtures_all_blocked": True,
        "testnet_base_url": "https://demo-fapi.binance.com",
        "order_test_path": "/fapi/v1/order/test",
        "external_runtime_order_test_adapter_enabled": False,
        "external_runtime_order_test_signer_injection_enabled": False,
        "external_runtime_order_test_transport_injection_enabled": False,
        "external_runtime_order_test_network_calls_enabled": False,
        "external_runtime_order_test_signing_enabled": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_enabled": False,
        "real_order_endpoint_called": False,
        "external_runtime_concrete_order_test_executor_included": False,
        "external_runtime_credential_reader_included": False,
        "real_signed_testnet_evidence_present": False,
        "redacted_real_order_test_evidence_exported": False,
        "actual_p7_import_ready": False,
        "actual_order_submission_performed": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "runtime_mutation_performed": False,
        "p61_real_testnet_order_test_dry_validation_adapter_sha256": "a" * 64,
    }
    atomic_write_json(
        root
        / "storage"
        / "latest"
        / "p61_real_testnet_order_test_dry_validation_adapter_report.json",
        payload,
    )


def test_p62_policy_defaults_are_testnet_order_test_only_and_disabled() -> None:
    policy = P62OperatorExecutionKitPolicy().to_dict()
    validation = validate_operator_execution_kit_policy(policy)
    assert validation["operator_execution_kit_policy_valid"] is True
    assert policy["base_url"] == "https://demo-fapi.binance.com"
    assert policy["path"] == "/fapi/v1/order/test"
    assert policy["kit_enabled"] is False
    assert policy["network_calls_enabled"] is False
    assert policy["real_order_submit_enabled"] is False


def test_p62_policy_blocks_enablement_and_raw_persistence() -> None:
    policy = replace(
        P62OperatorExecutionKitPolicy(),
        kit_enabled=True,
        network_calls_enabled=True,
        raw_response_persistence_allowed=True,
    ).to_dict()
    validation = validate_operator_execution_kit_policy(policy)
    assert validation["operator_execution_kit_policy_valid"] is False
    reasons = validation["operator_execution_kit_policy_block_reasons"]
    assert "P62_POLICY_KIT_ENABLED_NOT_FALSE" in reasons
    assert "P62_POLICY_NETWORK_CALLS_ENABLED_NOT_FALSE" in reasons
    assert "P62_POLICY_RAW_RESPONSE_PERSISTENCE_ALLOWED_NOT_FALSE" in reasons


def test_p62_manifest_is_separate_and_excluded_from_default_runtime() -> None:
    manifest = P62OperatorExecutionKitManifest().to_dict()
    validation = validate_operator_execution_kit_manifest(manifest)
    assert validation["operator_execution_kit_manifest_valid"] is True
    assert manifest["included_in_external_adapter_package"] is True
    assert manifest["included_in_default_runtime_candidate"] is False
    assert manifest["concrete_executor_included"] is False
    assert manifest["credential_reader_included"] is False


def test_p62_manifest_blocks_runtime_candidate_and_concrete_executor() -> None:
    manifest = replace(
        P62OperatorExecutionKitManifest(),
        included_in_default_runtime_candidate=True,
        concrete_executor_included=True,
    ).to_dict()
    validation = validate_operator_execution_kit_manifest(manifest)
    assert validation["operator_execution_kit_manifest_valid"] is False
    reasons = validation["operator_execution_kit_manifest_block_reasons"]
    assert "P62_MANIFEST_INCLUDED_IN_DEFAULT_RUNTIME_CANDIDATE_NOT_FALSE" in reasons
    assert "P62_MANIFEST_CONCRETE_EXECUTOR_INCLUDED_NOT_FALSE" in reasons


def test_p62_run_request_template_is_disabled_and_safe() -> None:
    request = P62OperatorRunRequest().to_dict()
    validation = validate_operator_run_request(
        request, require_run=False, allow_fixture=True
    )
    assert validation["operator_run_request_valid"] is True
    assert request["run_requested"] is False
    assert request["real_order_submit_allowed"] is False
    assert request["raw_credential_allowed"] is False


def test_p62_fixture_run_request_and_activation_validate_for_self_test() -> None:
    run_request = P62OperatorRunRequest(
        execution_scope=P62_NO_NETWORK_SELF_TEST_SCOPE,
        exact_operator_phrase=EXACT_P62_OPERATOR_KIT_PHRASE,
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
    ).to_dict()
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
    assert validate_operator_run_request(
        run_request, require_run=True, allow_fixture=True
    )["operator_run_request_valid"] is True
    assert validate_operator_execution_activation(
        activation, require_enabled=True, allow_fixture=True
    )["operator_execution_activation_valid"] is True


def test_p62_evidence_export_policy_is_redacted_only() -> None:
    policy = P62EvidenceExportPolicy().to_dict()
    validation = validate_evidence_export_policy(policy)
    assert validation["evidence_export_policy_valid"] is True
    assert policy["redacted_result_required"] is True
    assert policy["raw_request_allowed"] is False
    assert policy["raw_response_allowed"] is False
    assert policy["raw_credential_allowed"] is False


def test_p62_one_shot_guard_blocks_duplicate_and_releases_on_failure(tmp_path: Path) -> None:
    guard = P62OneShotRunGuard(tmp_path / "one_shot.json")
    marker = guard.acquire(nonce_sha256="1" * 64, request_sha256="2" * 64)
    assert marker["contains_secret_value"] is False
    with pytest.raises(AdapterPackageValidationError):
        guard.acquire(nonce_sha256="1" * 64, request_sha256="2" * 64)
    guard.release_after_failure()
    assert not (tmp_path / "one_shot.json").exists()


def test_p62_no_network_operator_kit_self_test_exports_redacted_bundle() -> None:
    report = build_p62_no_network_self_test()
    assert report["self_test_passed"] is True
    assert report["one_shot_guard_acquired"] is True
    assert report["duplicate_second_run_blocked"] is True
    assert report["redacted_evidence_export_completed"] is True
    assert report["no_secret_scan_passed"] is True
    assert report["p58_bridge_candidate_created"] is True
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["actual_order_submission_performed"] is False


def test_p62_default_real_path_is_blocked_and_submit_always_disabled(tmp_path: Path) -> None:
    kit = OperatorSideExternalOrderTestExecutionKit()
    with pytest.raises(AdapterPackageValidationError):
        kit.execute_approved_external_runtime_once(
            run_request=P62OperatorRunRequest(),
            activation=P62OperatorExecutionActivation(),
            p61_request=P61OrderTestRequestDescriptor(),
            p61_approval=P61OperatorOrderTestApproval(),
            p61_activation=P61ExternalRuntimeActivation(),
            executor=object(),  # type: ignore[arg-type]
            output_dir=tmp_path / "out",
            guard_path=tmp_path / "guard.json",
        )
    with pytest.raises(AdapterPackageDisabledError):
        kit.execute_real_order_submit()


def test_p62_negative_fixtures_all_blocked() -> None:
    report = build_p62_negative_fixture_results()
    assert report["fixture_count"] == 10
    assert report["all_negative_fixtures_blocked_fail_closed"] is True
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["actual_order_submission_performed"] is False


def test_p62_package_report_validated_but_disabled() -> None:
    report = build_p62_operator_execution_kit_package_report()
    assert report["status"] == STATUS_KIT_VALIDATED_DISABLED
    assert report["blocked"] is False
    assert report["operator_execution_kit_implemented"] is True
    assert report["one_shot_run_guard_implemented"] is True
    assert report["redacted_evidence_exporter_implemented"] is True
    assert report["operator_execution_kit_enabled"] is False
    assert report["real_order_test_endpoint_call_performed"] is False
    assert report["actual_order_submission_performed"] is False


def test_p62_source_validation_and_persist_expected_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_min_project(tmp_path)
    _write_p61_ready(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    source = read_json(
        tmp_path
        / "storage"
        / "latest"
        / "p61_real_testnet_order_test_dry_validation_adapter_report.json"
    )
    assert validate_p61_source(source)["p61_source_valid"] is True
    report = persist_p62_operator_side_external_order_test_execution_kit(cfg=cfg)
    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    latest = tmp_path / "storage" / "latest"
    expected = [
        "p62_operator_side_external_order_test_execution_kit_report.json",
        "p62_operator_execution_kit_policy_TEMPLATE_DISABLED.json",
        "p62_operator_execution_kit_manifest.json",
        "p62_operator_run_request_TEMPLATE_NO_CALL.json",
        "p62_operator_execution_activation_TEMPLATE_DISABLED.json",
        "p62_evidence_export_policy.json",
        "p62_operator_execution_kit_no_network_self_test_report.json",
        "p62_operator_execution_kit_negative_fixture_results.json",
        "p62_operator_side_external_order_test_execution_kit_summary.json",
        "p62_operator_side_external_order_test_execution_kit_registry_record.json",
    ]
    for name in expected:
        assert (latest / name).exists(), name
    saved = read_json(latest / expected[0])
    assert saved["operator_side_external_order_test_execution_kit_enabled"] is False
    assert saved["operator_side_external_order_test_endpoint_call_performed"] is False
    assert saved["http_request_sent"] is False
    assert saved["signature_created"] is False
    assert saved["secret_value_accessed"] is False
