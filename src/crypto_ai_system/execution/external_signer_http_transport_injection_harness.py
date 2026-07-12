from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from external_runtime_packages.binance_futures_testnet_adapter import (
    STATUS_HARNESS_VALIDATED_DISABLED,
    ExternalHttpTransportInjectionMetadata,
    ExternalSignerInjectionMetadata,
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

P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VERSION = "p60_external_signer_http_transport_injection_harness_v1"
P60_REGISTRY_NAME = "p60_external_signer_http_transport_injection_harness_registry"
STATUS_VALIDATED_REVIEW_ONLY_DISABLED = STATUS_HARNESS_VALIDATED_DISABLED
STATUS_BLOCKED_FAIL_CLOSED = "P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_BLOCKED_FAIL_CLOSED"


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
            "external_signer_transport_harness_implemented": True,
            "external_signer_transport_harness_enabled": False,
            "external_signer_injection_enabled": False,
            "external_http_transport_injection_enabled": False,
            "order_test_endpoint_dry_validation_enabled": True,
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
            "redacted_real_signed_testnet_evidence_exported": False,
            "actual_p7_import_ready": False,
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
    )
    return payload


def validate_p59_source(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers: list[str] = []
    if payload.get("status") != "P59_SEPARATE_TESTNET_EXTERNAL_ADAPTER_PACKAGE_VALIDATED_REVIEW_ONLY_ADAPTER_DISABLED":
        blockers.append("P60_P59_STATUS_INVALID")
    if payload.get("blocked") is True:
        blockers.append("P60_P59_SOURCE_BLOCKED")
    for key in (
        "external_runtime_adapter_package_created",
        "testnet_endpoint_policy_implemented",
        "metadata_only_key_binding_implemented",
        "external_process_memory_signer_protocol_implemented",
        "external_http_transport_protocol_implemented",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P60_P59_{key.upper()}_NOT_TRUE")
    for key in (
        "external_runtime_adapter_package_in_default_runtime_candidate",
        "external_runtime_adapter_runner_enabled",
        "external_runtime_adapter_network_calls_enabled",
        "external_runtime_adapter_signing_enabled",
        "external_runtime_adapter_submit_enabled",
        "external_runtime_concrete_transport_included",
        "external_runtime_concrete_signer_included",
        "external_runtime_secret_reader_included",
        "external_runtime_real_endpoint_execution_enabled",
        "real_signed_testnet_evidence_present",
        "actual_p7_import_ready",
        "actual_order_submission_performed",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
        "runtime_mutation_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P60_P59_{key.upper()}_NOT_FALSE")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P60_P59_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    validation = {
        "p59_source_valid": not blockers,
        "p59_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "p59_status": payload.get("status"),
    }
    validation["p60_p59_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_p60_external_signer_http_transport_injection_harness_report(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p59 = _read_latest_json(cfg, "p59_separate_testnet_external_adapter_package_report.json")
    p59_validation = validate_p59_source(p59)
    package_report = build_p60_harness_package_report()
    blockers = list(p59_validation["p59_source_block_reasons"])
    if package_report.get("status") != STATUS_HARNESS_VALIDATED_DISABLED:
        blockers.extend(package_report.get("block_reasons", []))
    flags = _execution_false_payload()
    unsafe = truthy_execution_flags({**package_report, **flags})
    if unsafe:
        blockers.append("P60_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    status = STATUS_BLOCKED_FAIL_CLOSED if blockers else STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    report = {
        "artifact_type": "p60_external_signer_http_transport_injection_harness_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p60_version": P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VERSION,
        "p59_source_status": p59.get("status"),
        "p59_source_sha256": p59.get("p59_separate_testnet_external_adapter_package_sha256"),
        "p59_source_validation": p59_validation,
        "external_harness_package_report": package_report,
        "external_signer_injection_harness_implemented": True,
        "external_http_transport_injection_harness_implemented": True,
        "order_test_endpoint_dry_validation_implemented": True,
        "order_test_endpoint_path": "/fapi/v1/order/test",
        "real_order_test_endpoint_call_enabled": False,
        "real_order_endpoint_enabled": False,
        "concrete_signer_implementation_included": False,
        "concrete_http_transport_implementation_included": False,
        "secret_reader_implementation_included": False,
        "no_network_harness_self_test_passed": package_report["no_network_harness_self_test"]["self_test_passed"],
        "negative_fixtures_all_blocked": package_report["negative_fixture_results"]["all_negative_fixtures_blocked_fail_closed"],
        "unsafe_truthy_execution_flags": unsafe,
        **flags,
    }
    report["p60_external_signer_http_transport_injection_harness_sha256"] = sha256_json(report)
    return report


def persist_p60_external_signer_http_transport_injection_harness(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_p60_external_signer_http_transport_injection_harness_report(cfg=cfg)
    package_report = report["external_harness_package_report"]
    harness_config = SignerTransportHarnessConfig().to_dict()
    signer_metadata = ExternalSignerInjectionMetadata().to_dict()
    transport_metadata = ExternalHttpTransportInjectionMetadata().to_dict()
    dry_intent = OrderTestDryValidationIntent().to_dict()
    self_test = build_p60_no_network_harness_self_test()
    negatives = build_p60_negative_fixture_results()
    summary = {
        "artifact_type": "p60_external_signer_http_transport_injection_harness_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "external_signer_transport_harness_implemented": True,
        "order_test_endpoint_dry_validation_implemented": True,
        "no_network_harness_self_test_passed": self_test["self_test_passed"],
        "negative_fixtures_all_blocked": negatives["all_negative_fixtures_blocked_fail_closed"],
        **_execution_false_payload(),
    }
    summary["p60_external_signer_http_transport_injection_harness_summary_sha256"] = sha256_json(summary)
    registry_record = {
        "artifact_type": "p60_external_signer_http_transport_injection_harness_registry_record",
        "record_id": stable_id("p60_external_signer_http_transport_harness", report["p60_external_signer_http_transport_injection_harness_sha256"]),
        "created_at_utc": utc_now_canonical(),
        "status": report["status"],
        "report_sha256": report["p60_external_signer_http_transport_injection_harness_sha256"],
        "review_only": True,
        "runtime_authority_source": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    registry_record["p60_external_signer_http_transport_injection_harness_registry_record_sha256"] = sha256_json(registry_record)
    artifacts = {
        "p60_external_signer_http_transport_injection_harness_report.json": report,
        "p60_signer_transport_harness_config_TEMPLATE_DISABLED.json": harness_config,
        "p60_external_signer_injection_metadata_TEMPLATE.json": signer_metadata,
        "p60_external_http_transport_injection_metadata_TEMPLATE.json": transport_metadata,
        "p60_order_test_dry_validation_intent_TEMPLATE_NO_SUBMIT.json": dry_intent,
        "p60_order_test_endpoint_no_network_dry_validation_report.json": self_test,
        "p60_signer_transport_harness_negative_fixture_results.json": negatives,
        "p60_external_signer_http_transport_injection_harness_summary.json": summary,
        "p60_external_signer_http_transport_injection_harness_registry_record.json": registry_record,
    }
    for name, payload in artifacts.items():
        atomic_write_json(latest / name, payload)
    append_registry_record(
        registry_path(cfg, P60_REGISTRY_NAME),
        registry_record,
        registry_name=P60_REGISTRY_NAME,
        id_field="record_id",
    )
    return report
