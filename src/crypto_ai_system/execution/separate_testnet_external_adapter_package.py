from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.external_adapter_review_contracts import (
    STATUS_PACKAGE_VALIDATED_ADAPTER_DISABLED,
    BinanceFuturesTestnetEndpointPolicy,
    DisabledExternalAdapterRunnerConfig,
    ExternalAdapterPackageManifest,
    MetadataOnlyKeyBinding,
    build_p59_adapter_package_report,
    build_p59_negative_fixture_results,
    build_p59_no_network_package_self_test,
    calculate_package_source_sha256,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_VERSION = "p59_separate_testnet_external_adapter_package_v1"
P59_REGISTRY_NAME = "p59_separate_testnet_external_adapter_package_registry"
STATUS_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED = STATUS_PACKAGE_VALIDATED_ADAPTER_DISABLED
STATUS_BLOCKED_FAIL_CLOSED = "P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_BLOCKED_FAIL_CLOSED"


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _execution_false_payload() -> dict[str, bool]:
    payload = default_execution_flag_state()
    payload.update(
        {
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
            "external_runtime_adapter_package_created": True,
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
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


def validate_p58_source(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers: list[str] = []
    if payload.get("status") != "P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_BOUNDARY_VALIDATED_REVIEW_ONLY_RUNNER_DISABLED":
        blockers.append("P59_P58_STATUS_INVALID")
    if payload.get("blocked") is True:
        blockers.append("P59_P58_SOURCE_BLOCKED")
    if payload.get("external_runtime_runner_implemented") is not True:
        blockers.append("P59_P58_RUNNER_NOT_IMPLEMENTED")
    if payload.get("external_runtime_adapter_protocol_implemented") is not True:
        blockers.append("P59_P58_ADAPTER_PROTOCOL_NOT_IMPLEMENTED")
    if payload.get("redacted_evidence_exporter_implemented") is not True:
        blockers.append("P59_P58_REDACTED_EXPORTER_NOT_IMPLEMENTED")
    for key in (
        "external_runtime_runner_enabled",
        "external_runtime_real_adapter_loaded",
        "external_runtime_real_acquisition_enabled",
        "external_runtime_real_acquisition_executed",
        "real_signed_testnet_evidence_present",
        "actual_p7_import_ready",
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "secret_value_accessed",
        "runtime_mutation_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P59_P58_{key.upper()}_NOT_FALSE")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P59_P58_UNSAFE_EXECUTION_FLAGS:" + ",".join(unsafe))
    validation = {
        "p58_source_valid": not blockers,
        "p58_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "p58_status": payload.get("status"),
    }
    validation["p59_p58_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_p59_separate_testnet_external_adapter_package_report(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p58 = _read_latest_json(cfg, "p58_external_runtime_evidence_acquisition_report.json")
    p58_validation = validate_p58_source(p58)
    package_report = build_p59_adapter_package_report()
    blockers = list(p58_validation["p58_source_block_reasons"])
    if package_report.get("status") != STATUS_PACKAGE_VALIDATED_ADAPTER_DISABLED:
        blockers.extend(package_report.get("block_reasons", []))
    flags = _execution_false_payload()
    unsafe = truthy_execution_flags({**package_report, **flags})
    if unsafe:
        blockers.append("P59_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    status = STATUS_BLOCKED_FAIL_CLOSED if blockers else STATUS_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED
    report = {
        "artifact_type": "p59_separate_testnet_external_adapter_package_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p59_version": P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_VERSION,
        "p58_source_status": p58.get("status"),
        "p58_source_sha256": p58.get("p58_external_runtime_evidence_acquisition_sha256"),
        "p58_source_validation": p58_validation,
        "external_adapter_package_report": package_report,
        "external_adapter_package_source_sha256": calculate_package_source_sha256(),
        "separate_external_runtime_package_created": True,
        "separate_external_runtime_package_zip_required": True,
        "default_runtime_candidate_must_exclude_external_adapter_package": True,
        "source_handoff_may_include_external_adapter_contract_and_tests": True,
        "adapter_orchestration_implemented": True,
        "testnet_endpoint_policy_implemented": True,
        "metadata_only_key_binding_implemented": True,
        "external_process_memory_signer_protocol_implemented": True,
        "external_http_transport_protocol_implemented": True,
        "concrete_network_transport_implementation_included": False,
        "concrete_signer_implementation_included": False,
        "secret_reader_implementation_included": False,
        "real_endpoint_execution_enabled": False,
        "no_network_package_self_test_passed": package_report["no_network_package_self_test"]["self_test_passed"],
        "negative_fixtures_all_blocked": package_report["negative_fixture_results"]["all_negative_fixtures_blocked_fail_closed"],
        "unsafe_truthy_execution_flags": unsafe,
        **flags,
    }
    report["p59_separate_testnet_external_adapter_package_sha256"] = sha256_json(report)
    return report


def persist_p59_separate_testnet_external_adapter_package(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_p59_separate_testnet_external_adapter_package_report(cfg=cfg)
    package_report = report["external_adapter_package_report"]
    policy = BinanceFuturesTestnetEndpointPolicy().to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256=sha256_json({"p59": "metadata-only-key-fingerprint"}),
        api_key_fingerprint_sha256=sha256_json({"p59": "metadata-only-api-key-fingerprint"}),
    ).to_dict()
    runner = DisabledExternalAdapterRunnerConfig().to_dict()
    manifest = ExternalAdapterPackageManifest(
        package_source_sha256=calculate_package_source_sha256()
    ).to_dict()
    self_test = build_p59_no_network_package_self_test()
    negatives = build_p59_negative_fixture_results()
    summary = {
        "artifact_type": "p59_separate_testnet_external_adapter_package_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "separate_external_runtime_package_created": True,
        "included_in_default_runtime_candidate": False,
        "no_network_package_self_test_passed": self_test["self_test_passed"],
        "negative_fixtures_all_blocked": negatives["all_negative_fixtures_blocked_fail_closed"],
        **_execution_false_payload(),
    }
    summary["p59_separate_testnet_external_adapter_package_summary_sha256"] = sha256_json(summary)
    registry_record = {
        "artifact_type": "p59_separate_testnet_external_adapter_package_registry_record",
        "record_id": stable_id("p59_external_adapter_package", report["p59_separate_testnet_external_adapter_package_sha256"]),
        "created_at_utc": utc_now_canonical(),
        "status": report["status"],
        "report_sha256": report["p59_separate_testnet_external_adapter_package_sha256"],
        "package_source_sha256": report["external_adapter_package_source_sha256"],
        "review_only": True,
        "runtime_authority_source": False,
        "actual_order_submission_performed": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
    }
    registry_record["p59_separate_testnet_external_adapter_package_registry_record_sha256"] = sha256_json(registry_record)

    artifacts = {
        "p59_separate_testnet_external_adapter_package_report.json": report,
        "p59_external_adapter_package_manifest.json": manifest,
        "p59_binance_futures_testnet_endpoint_policy.json": policy,
        "p59_metadata_only_key_binding_TEMPLATE.json": key_binding,
        "p59_disabled_external_adapter_runner_config.json": runner,
        "p59_no_network_external_adapter_package_self_test_report.json": self_test,
        "p59_external_adapter_package_negative_fixture_results.json": negatives,
        "p59_separate_testnet_external_adapter_package_summary.json": summary,
        "p59_separate_testnet_external_adapter_package_registry_record.json": registry_record,
    }
    for name, payload in artifacts.items():
        atomic_write_json(latest / name, payload)
    append_registry_record(
        registry_path(cfg, P59_REGISTRY_NAME),
        registry_record,
        registry_name=P59_REGISTRY_NAME,
        id_field="record_id",
    )
    return report
