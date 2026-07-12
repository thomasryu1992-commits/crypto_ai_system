from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.separate_testnet_external_adapter_package import (
    STATUS_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED,
    persist_p59_separate_testnet_external_adapter_package,
    validate_p58_source,
)
from external_runtime_packages.binance_futures_testnet_adapter import (
    ALLOWED_TESTNET_REST_BASE_URL,
    AdapterPackageDisabledError,
    BinanceFuturesTestnetAdapterSkeleton,
    BinanceFuturesTestnetEndpointPolicy,
    DisabledExternalAdapterRunnerConfig,
    ExternalAdapterPackageManifest,
    MetadataOnlyKeyBinding,
    build_p59_adapter_package_report,
    build_p59_negative_fixture_results,
    build_p59_no_network_package_self_test,
    calculate_package_source_sha256,
    validate_adapter_package_manifest,
    validate_disabled_runner_config,
    validate_endpoint_policy,
    validate_metadata_only_key_binding,
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
        "[project]\nname='tmp'\nversion='0.1.0'\n",
        encoding="utf-8",
    )


def _write_p58_ready(root: Path) -> None:
    payload = {
        "artifact_type": "p58_external_runtime_evidence_acquisition_report",
        "status": "P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_BOUNDARY_VALIDATED_REVIEW_ONLY_RUNNER_DISABLED",
        "blocked": False,
        "external_runtime_runner_implemented": True,
        "external_runtime_adapter_protocol_implemented": True,
        "redacted_evidence_exporter_implemented": True,
        "external_runtime_runner_enabled": False,
        "external_runtime_real_adapter_loaded": False,
        "external_runtime_real_acquisition_enabled": False,
        "external_runtime_real_acquisition_executed": False,
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "runtime_mutation_performed": False,
        "p58_external_runtime_evidence_acquisition_sha256": "a" * 64,
    }
    atomic_write_json(
        root / "storage" / "latest" / "p58_external_runtime_evidence_acquisition_report.json",
        payload,
    )


def test_p59_endpoint_policy_is_exact_testnet_only() -> None:
    policy = BinanceFuturesTestnetEndpointPolicy().to_dict()
    validation = validate_endpoint_policy(policy)
    assert validation["endpoint_policy_valid"] is True
    assert policy["rest_base_url"] == ALLOWED_TESTNET_REST_BASE_URL
    assert policy["symbol_allowlist"] == ["BTCUSDT"]
    assert policy["submit_path"] == "/fapi/v1/order"
    assert policy["status_path"] == "/fapi/v1/order"
    assert policy["cancel_path"] == "/fapi/v1/order"


def test_p59_endpoint_policy_rejects_mainnet_and_mutation_path() -> None:
    policy = replace(
        BinanceFuturesTestnetEndpointPolicy(),
        rest_base_url="https://fapi.binance.com",
        submit_path="/fapi/v1/leverage",
    ).to_dict()
    validation = validate_endpoint_policy(policy)
    assert validation["endpoint_policy_valid"] is False
    assert "P59_ENDPOINT_POLICY_BASE_URL_NOT_ALLOWED_TESTNET" in validation[
        "endpoint_policy_block_reasons"
    ]
    assert "P59_ENDPOINT_POLICY_SUBMIT_PATH_INVALID" in validation[
        "endpoint_policy_block_reasons"
    ]
    assert "P59_FORBIDDEN_ENDPOINT_PATH:submit_path" in validation[
        "endpoint_policy_block_reasons"
    ]


def test_p59_metadata_only_key_binding_rejects_raw_secret_and_secret_file_reads() -> None:
    binding = replace(
        MetadataOnlyKeyBinding(),
        raw_secret_value_included=True,
        secret_file_read_allowed=True,
    ).to_dict()
    validation = validate_metadata_only_key_binding(binding)
    assert validation["metadata_only_key_binding_valid"] is False
    assert "P59_KEY_BINDING_RAW_SECRET_VALUE_INCLUDED_NOT_FALSE" in validation[
        "metadata_only_key_binding_block_reasons"
    ]
    assert "P59_KEY_BINDING_SECRET_FILE_READ_ALLOWED_NOT_FALSE" in validation[
        "metadata_only_key_binding_block_reasons"
    ]


def test_p59_disabled_runner_rejects_enablement() -> None:
    config = replace(
        DisabledExternalAdapterRunnerConfig(),
        runner_enabled=True,
        network_calls_enabled=True,
        signing_enabled=True,
        submit_enabled=True,
    ).to_dict()
    validation = validate_disabled_runner_config(config)
    assert validation["disabled_runner_config_valid"] is False
    assert "P59_RUNNER_CONFIG_RUNNER_ENABLED_NOT_FALSE" in validation[
        "disabled_runner_config_block_reasons"
    ]
    assert "P59_RUNNER_CONFIG_NETWORK_CALLS_ENABLED_NOT_FALSE" in validation[
        "disabled_runner_config_block_reasons"
    ]
    assert "P59_RUNNER_CONFIG_SIGNING_ENABLED_NOT_FALSE" in validation[
        "disabled_runner_config_block_reasons"
    ]
    assert "P59_RUNNER_CONFIG_SUBMIT_ENABLED_NOT_FALSE" in validation[
        "disabled_runner_config_block_reasons"
    ]


def test_p59_manifest_requires_separate_package_and_exclusion_from_runtime_candidate() -> None:
    manifest = ExternalAdapterPackageManifest(
        package_source_sha256=calculate_package_source_sha256()
    ).to_dict()
    validation = validate_adapter_package_manifest(manifest)
    assert validation["adapter_package_manifest_valid"] is True
    assert manifest["package_scope"] == "separate_external_runtime_package_only"
    assert manifest["included_in_default_runtime_candidate"] is False
    assert manifest["concrete_network_transport_implementation_included"] is False
    assert manifest["concrete_signer_implementation_included"] is False


def test_p59_adapter_skeleton_builds_unsigned_plan_without_network_signature_or_secret() -> None:
    adapter = BinanceFuturesTestnetAdapterSkeleton()
    result = adapter.execute_no_network_contract_self_test()
    assert result["unsigned_request_plan_built"] is True
    assert result["runner_enabled"] is False
    assert result["network_calls_enabled"] is False
    assert result["signing_enabled"] is False
    assert result["submit_enabled"] is False
    assert result["order_endpoint_called"] is False
    assert result["http_request_sent"] is False
    assert result["signature_created"] is False
    assert result["secret_value_accessed"] is False


def test_p59_real_execution_path_is_disabled() -> None:
    with pytest.raises(AdapterPackageDisabledError):
        BinanceFuturesTestnetAdapterSkeleton().execute_real_signed_testnet_order()


def test_p59_no_network_self_test_passes_and_real_path_stays_blocked() -> None:
    report = build_p59_no_network_package_self_test()
    assert report["self_test_passed"] is True
    assert report["real_execution_path_blocked"] is True
    assert report["actual_order_submission_performed"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False


def test_p59_negative_fixtures_all_fail_closed() -> None:
    report = build_p59_negative_fixture_results()
    assert report["fixture_count"] == 10
    assert report["all_negative_fixtures_blocked_fail_closed"] is True


def test_p59_package_report_validated_but_adapter_disabled() -> None:
    report = build_p59_adapter_package_report()
    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED
    assert report["blocked"] is False
    assert report["separate_external_runtime_package_created"] is True
    assert report["included_in_default_runtime_candidate"] is False
    assert report["adapter_orchestration_implemented"] is True
    assert report["concrete_network_transport_implementation_included"] is False
    assert report["concrete_signer_implementation_included"] is False
    assert report["real_endpoint_call_implementation_enabled"] is False
    assert report["actual_order_submission_performed"] is False


def test_p59_rejects_unsafe_p58_source() -> None:
    source = {
        "status": "P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_BOUNDARY_VALIDATED_REVIEW_ONLY_RUNNER_DISABLED",
        "blocked": False,
        "external_runtime_runner_implemented": True,
        "external_runtime_adapter_protocol_implemented": True,
        "redacted_evidence_exporter_implemented": True,
        "external_runtime_runner_enabled": True,
    }
    validation = validate_p58_source(source)
    assert validation["p58_source_valid"] is False
    assert "P59_P58_EXTERNAL_RUNTIME_RUNNER_ENABLED_NOT_FALSE" in validation[
        "p58_source_block_reasons"
    ]


def test_p59_main_report_and_persistence_keep_all_execution_disabled(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p58_ready(tmp_path)
    cfg = load_config(tmp_path)
    report = persist_p59_separate_testnet_external_adapter_package(cfg=cfg)
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED
    assert report["external_runtime_adapter_runner_enabled"] is False
    assert report["external_runtime_adapter_network_calls_enabled"] is False
    assert report["external_runtime_adapter_signing_enabled"] is False
    assert report["external_runtime_adapter_submit_enabled"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert (latest / "p59_external_adapter_package_manifest.json").exists()
    assert (latest / "p59_binance_futures_testnet_endpoint_policy.json").exists()
    summary = read_json(
        latest / "p59_separate_testnet_external_adapter_package_summary.json",
        default={},
    )
    assert summary["included_in_default_runtime_candidate"] is False


def test_p59_package_split_builds_separate_adapter_zip_and_excludes_it_from_runtime(
    tmp_path: Path,
) -> None:
    from scripts.build_p45_package_splits import build_package_splits

    project = tmp_path / "project"
    package_dir = project / "external_runtime_packages" / "binance_futures_testnet_adapter"
    package_dir.mkdir(parents=True)
    (project / "external_runtime_packages" / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "adapter_package.py").write_text("VALUE=1\n", encoding="utf-8")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("VALUE=1\n", encoding="utf-8")
    (project / "README.md").write_text("test\n", encoding="utf-8")

    manifest = build_package_splits(project, tmp_path / "dist")
    adapter_zip = Path(manifest["outputs"]["external_runtime_adapter_package"]["path"])
    runtime_zip = Path(manifest["outputs"]["runtime_candidate_package"]["path"])
    assert adapter_zip.exists()
    with zipfile.ZipFile(adapter_zip) as zf:
        assert any(name.endswith("adapter_package.py") for name in zf.namelist())
    with zipfile.ZipFile(runtime_zip) as zf:
        assert not any("external_runtime_packages" in name for name in zf.namelist())
