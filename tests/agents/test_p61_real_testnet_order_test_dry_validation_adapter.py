from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.real_testnet_order_test_dry_validation_adapter import (
    STATUS_VALIDATED_REVIEW_ONLY_DISABLED,
    persist_p61_real_testnet_order_test_dry_validation_adapter,
    validate_p60_source,
)
from external_runtime_packages.binance_futures_testnet_adapter import (
    EXACT_ORDER_TEST_APPROVAL_PHRASE,
    NO_NETWORK_SELF_TEST_SCOPE,
    AdapterPackageDisabledError,
    AdapterPackageValidationError,
    P61ExternalExecutorMetadata,
    P61ExternalRuntimeActivation,
    P61OperatorOrderTestApproval,
    P61OrderTestAdapterPolicy,
    P61OrderTestRequestDescriptor,
    RealTestnetOrderTestDryValidationAdapter,
    STATUS_ADAPTER_VALIDATED_DISABLED,
    build_p61_adapter_package_report,
    build_p61_negative_fixture_results,
    build_p61_no_network_self_test,
    validate_external_executor_metadata,
    validate_external_runtime_activation,
    validate_operator_order_test_approval,
    validate_order_test_adapter_policy,
    validate_order_test_request_descriptor,
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


def _write_p60_ready(root: Path) -> None:
    payload = {
        "artifact_type": "p60_external_signer_http_transport_injection_harness_report",
        "status": "P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VALIDATED_REVIEW_ONLY_DISABLED",
        "blocked": False,
        "external_signer_transport_harness_implemented": True,
        "external_signer_injection_harness_implemented": True,
        "external_http_transport_injection_harness_implemented": True,
        "order_test_endpoint_dry_validation_implemented": True,
        "order_test_endpoint_path": "/fapi/v1/order/test",
        "external_signer_transport_harness_enabled": False,
        "external_signer_injection_enabled": False,
        "external_http_transport_injection_enabled": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_endpoint_enabled": False,
        "external_runtime_adapter_runner_enabled": False,
        "external_runtime_adapter_network_calls_enabled": False,
        "external_runtime_adapter_signing_enabled": False,
        "external_runtime_adapter_submit_enabled": False,
        "external_runtime_concrete_transport_included": False,
        "external_runtime_concrete_signer_included": False,
        "external_runtime_secret_reader_included": False,
        "external_runtime_real_endpoint_execution_enabled": False,
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        "actual_order_submission_performed": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "runtime_mutation_performed": False,
        "p60_external_signer_http_transport_injection_harness_sha256": "a" * 64,
    }
    atomic_write_json(
        root
        / "storage"
        / "latest"
        / "p60_external_signer_http_transport_injection_harness_report.json",
        payload,
    )


def test_p61_policy_defaults_are_testnet_order_test_only_and_disabled() -> None:
    policy = P61OrderTestAdapterPolicy().to_dict()
    validation = validate_order_test_adapter_policy(policy)
    assert validation["order_test_adapter_policy_valid"] is True
    assert policy["base_url"] == "https://demo-fapi.binance.com"
    assert policy["path"] == "/fapi/v1/order/test"
    assert policy["adapter_enabled"] is False
    assert policy["network_calls_enabled"] is False
    assert policy["real_order_submit_endpoint_enabled"] is False


def test_p61_policy_blocks_network_signing_and_real_submit_enablement() -> None:
    policy = replace(
        P61OrderTestAdapterPolicy(),
        network_calls_enabled=True,
        signing_enabled=True,
        real_order_submit_endpoint_enabled=True,
    ).to_dict()
    validation = validate_order_test_adapter_policy(policy)
    assert validation["order_test_adapter_policy_valid"] is False
    reasons = validation["order_test_adapter_policy_block_reasons"]
    assert "P61_POLICY_NETWORK_CALLS_ENABLED_NOT_FALSE" in reasons
    assert "P61_POLICY_SIGNING_ENABLED_NOT_FALSE" in reasons
    assert "P61_POLICY_REAL_ORDER_SUBMIT_ENDPOINT_ENABLED_NOT_FALSE" in reasons


def test_p61_request_descriptor_is_deterministic_and_safe() -> None:
    request = P61OrderTestRequestDescriptor().to_dict()
    validation = validate_order_test_request_descriptor(request)
    assert validation["order_test_request_descriptor_valid"] is True
    assert request["path"] == "/fapi/v1/order/test"
    assert request["fixture_only"] is True
    assert request["real_order_submit_requested"] is False
    assert len(request["canonical_query_sha256"]) == 64


def test_p61_request_descriptor_blocks_wrong_symbol_and_submit_request() -> None:
    request = replace(
        P61OrderTestRequestDescriptor(),
        symbol="ETHUSDT",
        real_order_submit_requested=True,
    ).to_dict()
    validation = validate_order_test_request_descriptor(request)
    assert validation["order_test_request_descriptor_valid"] is False
    reasons = validation["order_test_request_descriptor_block_reasons"]
    assert "P61_REQUEST_SYMBOL_INVALID" in reasons
    assert "P61_REQUEST_REAL_ORDER_SUBMIT_REQUESTED_NOT_FALSE" in reasons


def test_p61_external_executor_metadata_is_external_only_not_packaged() -> None:
    metadata = P61ExternalExecutorMetadata().to_dict()
    validation = validate_external_executor_metadata(metadata)
    assert validation["external_executor_metadata_valid"] is True
    assert metadata["external_runtime_only"] is True
    assert metadata["included_in_review_package"] is False
    assert metadata["included_in_default_runtime_candidate"] is False


def test_p61_external_executor_metadata_blocks_mainnet_or_packaging() -> None:
    metadata = replace(
        P61ExternalExecutorMetadata(),
        base_url="https://fapi.binance.com",
        included_in_review_package=True,
    ).to_dict()
    validation = validate_external_executor_metadata(metadata)
    assert validation["external_executor_metadata_valid"] is False
    reasons = validation["external_executor_metadata_block_reasons"]
    assert "P61_EXECUTOR_BASE_URL_INVALID" in reasons
    assert "P61_EXECUTOR_INCLUDED_IN_REVIEW_PACKAGE_NOT_FALSE" in reasons


def test_p61_operator_approval_template_is_not_granted() -> None:
    approval = P61OperatorOrderTestApproval().to_dict()
    validation = validate_operator_order_test_approval(
        approval, require_granted=False, allow_fixture=True
    )
    assert validation["operator_order_test_approval_valid"] is True
    assert approval["approval_granted"] is False
    assert approval["real_order_submit_allowed"] is False


def test_p61_fixture_approval_and_activation_validate_only_for_self_test() -> None:
    request = P61OrderTestRequestDescriptor().to_dict()
    approval = P61OperatorOrderTestApproval(
        exact_approval_phrase=EXACT_ORDER_TEST_APPROVAL_PHRASE,
        operator_confirmation_sha256="1" * 64,
        source_p60_report_sha256="2" * 64,
        request_descriptor_sha256=request["p61_order_test_request_descriptor_sha256"],
        key_fingerprint_sha256="3" * 64,
        approval_granted=True,
        fixture_only=True,
    ).to_dict()
    approval_validation = validate_operator_order_test_approval(
        approval, require_granted=True, allow_fixture=True
    )
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
    assert approval_validation["operator_order_test_approval_valid"] is True
    assert activation_validation["external_runtime_activation_valid"] is True


def test_p61_no_network_injected_executor_self_test_passes_without_endpoint_call() -> None:
    report = build_p61_no_network_self_test()
    assert report["self_test_passed"] is True
    assert report["approved_real_path_blocked_with_default_disabled_inputs"] is True
    assert report["real_order_submit_path_blocked"] is True
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["actual_order_submission_performed"] is False


def test_p61_default_real_path_is_blocked_and_submit_path_always_disabled() -> None:
    adapter = RealTestnetOrderTestDryValidationAdapter()
    with pytest.raises(AdapterPackageValidationError):
        adapter.execute_approved_external_runtime_order_test(
            request=P61OrderTestRequestDescriptor(),
            approval=P61OperatorOrderTestApproval(),
            activation=P61ExternalRuntimeActivation(),
            executor=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(AdapterPackageDisabledError):
        adapter.execute_real_order_submit()


def test_p61_negative_fixtures_all_blocked() -> None:
    report = build_p61_negative_fixture_results()
    assert report["fixture_count"] == 10
    assert report["all_negative_fixtures_blocked_fail_closed"] is True
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["actual_order_submission_performed"] is False


def test_p61_package_report_validated_but_disabled() -> None:
    report = build_p61_adapter_package_report()
    assert report["status"] == STATUS_ADAPTER_VALIDATED_DISABLED
    assert report["blocked"] is False
    assert report["real_order_test_adapter_implemented"] is True
    assert report["approved_external_runtime_order_test_path_implemented"] is True
    assert report["concrete_external_executor_included"] is False
    assert report["real_order_test_endpoint_call_enabled"] is False
    assert report["http_request_sent"] is False
    assert report["actual_order_submission_performed"] is False


def test_p61_source_validation_and_persist_expected_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_min_project(tmp_path)
    _write_p60_ready(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    source = read_json(
        tmp_path
        / "storage"
        / "latest"
        / "p60_external_signer_http_transport_injection_harness_report.json"
    )
    assert validate_p60_source(source)["p60_source_valid"] is True
    report = persist_p61_real_testnet_order_test_dry_validation_adapter(cfg=cfg)
    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    latest = tmp_path / "storage" / "latest"
    expected = [
        "p61_real_testnet_order_test_dry_validation_adapter_report.json",
        "p61_order_test_adapter_policy_TEMPLATE_DISABLED.json",
        "p61_external_signed_order_test_executor_metadata_TEMPLATE.json",
        "p61_operator_order_test_approval_TEMPLATE_NO_CALL.json",
        "p61_order_test_request_descriptor_TEMPLATE_NO_CALL.json",
        "p61_external_runtime_activation_TEMPLATE_DISABLED.json",
        "p61_order_test_no_network_injected_executor_self_test_report.json",
        "p61_real_order_test_adapter_negative_fixture_results.json",
        "p61_real_testnet_order_test_dry_validation_adapter_summary.json",
        "p61_real_testnet_order_test_dry_validation_adapter_registry_record.json",
    ]
    for name in expected:
        assert (latest / name).exists(), name
    saved = read_json(latest / expected[0])
    assert saved["real_order_test_endpoint_call_performed"] is False
    assert saved["real_order_endpoint_called"] is False
    assert saved["http_request_sent"] is False
    assert saved["signature_created"] is False
    assert saved["secret_value_accessed"] is False
