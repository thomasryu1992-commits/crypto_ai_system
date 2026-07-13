from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.external_signer_http_transport_injection_harness import (
    STATUS_VALIDATED_REVIEW_ONLY_DISABLED,
    persist_p60_external_signer_http_transport_injection_harness,
    validate_p59_source,
)
from external_runtime_packages.binance_futures_testnet_adapter import (
    AdapterPackageDisabledError,
    ExternalHttpTransportInjectionMetadata,
    ExternalSignerInjectionMetadata,
    ExternalSignerTransportInjectionHarness,
    OrderTestDryValidationIntent,
    SignerTransportHarnessConfig,
    build_p60_harness_package_report,
    build_p60_negative_fixture_results,
    build_p60_no_network_harness_self_test,
    validate_harness_config,
    validate_order_test_dry_validation_intent,
    validate_signer_injection_metadata,
    validate_transport_injection_metadata,
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
    (root / "pyproject.toml").write_text("[project]\nname='tmp'\nversion='0.1.0'\n", encoding="utf-8")


def _write_p59_ready(root: Path) -> None:
    payload = {
        "artifact_type": "p59_separate_testnet_external_adapter_package_report",
        "status": "P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED",
        "blocked": False,
        "external_runtime_adapter_package_created": True,
        "testnet_endpoint_policy_implemented": True,
        "metadata_only_key_binding_implemented": True,
        "external_process_memory_signer_protocol_implemented": True,
        "external_http_transport_protocol_implemented": True,
        "external_runtime_adapter_package_in_default_runtime_candidate": False,
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
        "p59_separate_testnet_external_adapter_package_sha256": "b" * 64,
    }
    atomic_write_json(root / "storage" / "latest" / "p59_separate_testnet_external_adapter_package_report.json", payload)


def test_p60_harness_config_defaults_are_disabled_but_order_test_dry_validation_allowed() -> None:
    config = SignerTransportHarnessConfig().to_dict()
    validation = validate_harness_config(config)
    assert validation["harness_config_valid"] is True
    assert config["harness_enabled"] is False
    assert config["signing_enabled"] is False
    assert config["network_calls_enabled"] is False
    assert config["submit_enabled"] is False
    assert config["allowed_dry_validation_path"] == "/fapi/v1/order/test"


def test_p60_harness_config_rejects_signing_network_or_wrong_path() -> None:
    config = replace(
        SignerTransportHarnessConfig(),
        signing_enabled=True,
        network_calls_enabled=True,
        allowed_dry_validation_path="/fapi/v1/order",
    ).to_dict()
    validation = validate_harness_config(config)
    assert validation["harness_config_valid"] is False
    reasons = validation["harness_config_block_reasons"]
    assert "P60_HARNESS_SIGNING_ENABLED_NOT_FALSE" in reasons
    assert "P60_HARNESS_NETWORK_CALLS_ENABLED_NOT_FALSE" in reasons
    assert "P60_HARNESS_DRY_VALIDATION_PATH_INVALID" in reasons


def test_p60_signer_metadata_rejects_secret_persistence_and_enabled_signing() -> None:
    metadata = replace(
        ExternalSignerInjectionMetadata(),
        secret_persistence_allowed=True,
        signature_creation_enabled_by_default=True,
    ).to_dict()
    validation = validate_signer_injection_metadata(metadata)
    assert validation["signer_injection_metadata_valid"] is False
    assert "P60_SIGNER_SECRET_PERSISTENCE_ALLOWED_NOT_FALSE" in validation["signer_injection_metadata_block_reasons"]
    assert "P60_SIGNER_SIGNATURE_CREATION_ENABLED_BY_DEFAULT_NOT_FALSE" in validation["signer_injection_metadata_block_reasons"]


def test_p60_transport_metadata_rejects_mainnet_and_network_send() -> None:
    metadata = replace(
        ExternalHttpTransportInjectionMetadata(),
        base_url="https://fapi.binance.com",
        real_network_send_enabled_by_default=True,
    ).to_dict()
    validation = validate_transport_injection_metadata(metadata)
    assert validation["transport_injection_metadata_valid"] is False
    assert "P60_TRANSPORT_BASE_URL_NOT_ALLOWED_TESTNET" in validation["transport_injection_metadata_block_reasons"]
    assert "P60_TRANSPORT_REAL_NETWORK_SEND_ENABLED_BY_DEFAULT_NOT_FALSE" in validation["transport_injection_metadata_block_reasons"]


def test_p60_dry_validation_intent_rejects_real_evidence_or_submit_request() -> None:
    intent = replace(
        OrderTestDryValidationIntent(),
        signed_testnet_real_evidence=True,
        submit_requested=True,
        signature_requested=True,
    ).to_dict()
    validation = validate_order_test_dry_validation_intent(intent)
    assert validation["order_test_dry_validation_intent_valid"] is False
    assert "P60_DRY_INTENT_SIGNED_TESTNET_REAL_EVIDENCE_NOT_FALSE" in validation["order_test_dry_validation_intent_block_reasons"]
    assert "P60_DRY_INTENT_SUBMIT_REQUESTED_NOT_FALSE" in validation["order_test_dry_validation_intent_block_reasons"]


def test_p60_harness_builds_order_test_dry_validation_plan_without_signature_or_network() -> None:
    plan = ExternalSignerTransportInjectionHarness().build_order_test_dry_validation_plan()
    assert plan["path"] == "/fapi/v1/order/test"
    assert plan["method"] == "POST"
    assert plan["dry_validation_only"] is True
    assert plan["signature_created"] is False
    assert plan["signed_request_created"] is False
    assert plan["http_request_sent"] is False
    assert plan["secret_value_accessed"] is False


def test_p60_no_network_self_test_blocks_real_paths() -> None:
    report = build_p60_no_network_harness_self_test()
    assert report["self_test_passed"] is True
    assert report["real_dry_validation_path_blocked"] is True
    assert report["real_submit_path_blocked"] is True
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False


def test_p60_real_execution_methods_raise_disabled_errors() -> None:
    harness = ExternalSignerTransportInjectionHarness()
    with pytest.raises(AdapterPackageDisabledError):
        harness.execute_real_order_test_dry_validation()
    with pytest.raises(AdapterPackageDisabledError):
        harness.execute_real_signed_testnet_submit()


def test_p60_negative_fixtures_all_blocked() -> None:
    report = build_p60_negative_fixture_results()
    assert report["fixture_count"] == 10
    assert report["all_negative_fixtures_blocked_fail_closed"] is True
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False


def test_p60_package_report_validated_and_disabled() -> None:
    report = build_p60_harness_package_report()
    assert report["status"] == "P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VALIDATED_REVIEW_ONLY_DISABLED"
    assert report["blocked"] is False
    assert report["order_test_endpoint_dry_validation_implemented"] is True
    assert report["concrete_signer_included"] is False
    assert report["concrete_http_transport_included"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False


def test_p60_p59_source_validation_blocks_unsafe_source() -> None:
    validation = validate_p59_source({"status": "bad", "external_runtime_adapter_runner_enabled": True})
    assert validation["p59_source_valid"] is False
    assert "P60_P59_STATUS_INVALID" in validation["p59_source_block_reasons"]


def test_p60_persist_writes_expected_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_min_project(tmp_path)
    _write_p59_ready(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    report = persist_p60_external_signer_http_transport_injection_harness(cfg=cfg)
    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    latest = tmp_path / "storage" / "latest"
    expected = [
        "p60_external_signer_http_transport_injection_harness_report.json",
        "p60_signer_transport_harness_config_TEMPLATE_DISABLED.json",
        "p60_external_signer_injection_metadata_TEMPLATE.json",
        "p60_external_http_transport_injection_metadata_TEMPLATE.json",
        "p60_order_test_dry_validation_intent_TEMPLATE_NO_SUBMIT.json",
        "p60_order_test_endpoint_no_network_dry_validation_report.json",
        "p60_signer_transport_harness_negative_fixture_results.json",
        "p60_external_signer_http_transport_injection_harness_summary.json",
        "p60_external_signer_http_transport_injection_harness_registry_record.json",
    ]
    for name in expected:
        assert (latest / name).exists(), name
    saved = read_json(latest / "p60_external_signer_http_transport_injection_harness_report.json")
    assert saved["http_request_sent"] is False
    assert saved["signature_created"] is False
    assert saved["secret_value_accessed"] is False


def test_p60_blocks_raw_secret_field_in_intent() -> None:
    payload = OrderTestDryValidationIntent().to_dict()
    payload["api_secret_value"] = "super-secret"
    validation = validate_order_test_dry_validation_intent(payload)
    assert validation["order_test_dry_validation_intent_valid"] is False
    assert any(reason.startswith("P59_FORBIDDEN_SECRET_OR_RAW_FIELD") for reason in validation["order_test_dry_validation_intent_block_reasons"])
