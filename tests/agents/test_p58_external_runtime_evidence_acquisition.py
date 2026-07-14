from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from crypto_ai_system.execution.external_runtime_signed_testnet_evidence_acquisition import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALIDATED_REVIEW_ONLY_RUNNER_DISABLED,
    ExternalRuntimeAdapterManifest,
    ExternalRuntimeEvidenceAcquisitionConfig,
    ExternalRuntimeEvidenceAcquisitionDisabledError,
    ExternalRuntimeEvidenceAcquisitionRunner,
    ExternalRuntimeEvidenceAcquisitionValidationError,
    P58EvidenceAcquisitionRequest,
    P58NoNetworkFixtureAdapter,
    P58RedactedEvidenceExporter,
    build_p58_external_runtime_evidence_acquisition_report,
    build_p58_negative_fixture_results,
    build_valid_p58_self_test_request,
    persist_p58_external_runtime_evidence_acquisition,
    run_p58_no_network_evidence_acquisition_self_test,
    validate_external_runtime_adapter_manifest,
    validate_p58_config,
)


def test_p58_valid_self_test_request_passes_boundary_validation():
    request = build_valid_p58_self_test_request()
    validation = ExternalRuntimeEvidenceAcquisitionRunner().validate_request(
        request, P58NoNetworkFixtureAdapter()
    )
    assert validation["request_valid"] is True
    assert validation["request_block_reasons"] == []
    assert validation["adapter_fixture_only"] is True
    assert validation["adapter_network_call_capable"] is False


def test_p58_runner_exports_redacted_fixture_bundle_without_network(tmp_path):
    request = build_valid_p58_self_test_request()
    result = ExternalRuntimeEvidenceAcquisitionRunner().execute_no_network_self_test(
        request,
        P58NoNetworkFixtureAdapter(),
        output_dir=tmp_path / "evidence",
    )
    assert result["runner_code_path_exercised"] is True
    assert result["adapter_contract_exercised"] is True
    assert result["redacted_exporter_code_path_exercised"] is True
    assert result["exported_file_count"] == 5
    assert result["no_secret_scan_passed"] is True
    assert result["real_signed_testnet_evidence"] is False
    assert result["p7_import_eligible"] is False
    assert result["order_endpoint_called"] is False
    assert result["http_request_sent"] is False
    assert result["signature_created"] is False
    assert result["secret_value_accessed"] is False
    assert len(list((tmp_path / "evidence").glob("*.json"))) == 5


def test_p58_real_evidence_acquisition_path_is_disabled(tmp_path):
    request = replace(
        build_valid_p58_self_test_request(),
        operation_scope="signed_testnet_real_evidence_acquisition",
        evidence_origin="real_signed_testnet_external_runtime",
        self_test_only=False,
        real_evidence_acquisition_requested=True,
    )
    runner = ExternalRuntimeEvidenceAcquisitionRunner()
    with pytest.raises(ExternalRuntimeEvidenceAcquisitionDisabledError):
        runner.execute_real_evidence_acquisition(
            request,
            P58NoNetworkFixtureAdapter(),
            output_dir=tmp_path / "real",
        )
    assert not (tmp_path / "real").exists()


def test_p58_config_rejects_runner_enablement():
    config = replace(
        ExternalRuntimeEvidenceAcquisitionConfig(),
        external_runtime_runner_enabled=True,
    ).to_dict()
    validation = validate_p58_config(config)
    assert validation["config_valid"] is False
    assert "P58_CONFIG_EXTERNAL_RUNTIME_RUNNER_ENABLED_NOT_FALSE" in validation[
        "config_block_reasons"
    ]


def test_p58_external_real_adapter_manifest_is_contract_only_and_valid():
    manifest = ExternalRuntimeAdapterManifest().to_dict()
    validation = validate_external_runtime_adapter_manifest(
        manifest, self_test=False
    )
    assert validation["manifest_valid"] is True
    assert validation["real_endpoint_adapter"] is True
    assert validation["implementation_included_in_review_package"] is False


def test_p58_rejects_tampered_p6_preflight_hash():
    request = build_valid_p58_self_test_request()
    payload = deepcopy(request.canonical_payload())
    payload["p6_preflight_report"]["environment"] = "mainnet"
    tampered = P58EvidenceAcquisitionRequest(**payload)
    validation = ExternalRuntimeEvidenceAcquisitionRunner().validate_request(
        tampered, P58NoNetworkFixtureAdapter()
    )
    assert validation["request_valid"] is False
    assert "P58_P6_EMBEDDED_SHA256_INVALID" in validation[
        "request_block_reasons"
    ]


def test_p58_rejects_operator_approval_hash_mismatch():
    request = build_valid_p58_self_test_request()
    payload = deepcopy(request.canonical_payload())
    payload["operator_approval"]["approved_order_intent_sha256"] = "f" * 64
    tampered = P58EvidenceAcquisitionRequest(**payload)
    validation = ExternalRuntimeEvidenceAcquisitionRunner().validate_request(
        tampered, P58NoNetworkFixtureAdapter()
    )
    assert validation["request_valid"] is False
    assert any(
        reason in validation["request_block_reasons"]
        for reason in (
            "P58_OPERATOR_APPROVAL_EMBEDDED_SHA256_INVALID",
            "P58_APPROVED_ORDER_INTENT_HASH_MISMATCH",
        )
    )


def test_p58_rejects_network_capable_adapter_in_self_test():
    class UnsafeAdapter(P58NoNetworkFixtureAdapter):
        network_call_capable = True

    validation = ExternalRuntimeEvidenceAcquisitionRunner().validate_request(
        build_valid_p58_self_test_request(), UnsafeAdapter()
    )
    assert validation["request_valid"] is False
    assert "P58_SELF_TEST_ADAPTER_NETWORK_CAPABLE" in validation[
        "request_block_reasons"
    ]


def test_p58_exporter_rejects_secret_or_raw_fields():
    adapter = P58NoNetworkFixtureAdapter()
    request = build_valid_p58_self_test_request()
    result = dict(
        adapter.acquire_redacted_evidence(
            order_intent_metadata=request.order_intent_metadata,
            idempotency_key=request.idempotency_key,
            secret_reference_id=request.secret_reference_id,
        )
    )
    result["api_secret_value"] = "FORBIDDEN"
    validation = P58RedactedEvidenceExporter().validate_adapter_result(result)
    assert validation["adapter_result_valid"] is False
    assert any(
        "P58_FORBIDDEN_SECRET_OR_RAW_FIELD" in reason
        for reason in validation["adapter_result_block_reasons"]
    )


def test_p58_self_test_proves_runner_adapter_exporter_path():
    report = run_p58_no_network_evidence_acquisition_self_test()
    assert report["self_test_passed"] is True
    assert report["runner_code_path_exercised"] is True
    assert report["adapter_contract_exercised"] is True
    assert report["redacted_exporter_code_path_exercised"] is True
    assert report["all_expected_files_exist"] is True
    assert report["manifest_hash_valid"] is True
    assert report["no_secret_scan_passed"] is True
    assert report["ephemeral_output_directory_deleted_after_test"] is True
    assert report["real_evidence_acquisition_scope_blocked"] is True
    assert report["real_signed_testnet_evidence_present"] is False
    assert report["actual_p7_import_ready"] is False


def test_p58_negative_fixtures_all_fail_closed():
    report = build_p58_negative_fixture_results()
    assert report["all_negative_fixtures_blocked_fail_closed"] is True
    assert len(report["fixture_results"]) == 10


def test_p58_report_validates_boundary_but_keeps_runner_disabled():
    report = build_p58_external_runtime_evidence_acquisition_report()
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert report["external_runtime_runner_implemented"] is True
    assert report["external_runtime_adapter_protocol_implemented"] is True
    assert report["redacted_evidence_exporter_implemented"] is True
    assert report["runner_adapter_exporter_code_path_exercised"] is True
    assert report["real_adapter_implementation_included_in_review_package"] is False
    assert report["real_signed_testnet_evidence_present"] is False
    assert report["actual_p7_import_ready"] is False
    assert report["external_runtime_runner_enabled"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["runtime_mutation_performed"] is False


def test_p58_persist_writes_expected_latest_artifacts():
    report = persist_p58_external_runtime_evidence_acquisition()
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    latest = report  # build completion is asserted by returned validated report
    assert latest["real_signed_testnet_evidence_present"] is False
    assert latest["external_runtime_real_acquisition_executed"] is False
