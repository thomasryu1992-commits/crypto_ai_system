from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
    truthy_execution_flags,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from external_runtime_packages.binance_futures_testnet_adapter import (
    P63ConcreteExecutorActivation,
    P63ConcreteExecutorPackageManifest,
    P63ConcreteExecutorPolicy,
    P63ExecutorIntegrationRequest,
    P63OpaqueSenderMetadata,
    STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED,
    build_p63_concrete_executor_package_report,
    build_p63_negative_fixture_results,
    build_p63_no_network_integration_self_test,
)

P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VERSION = (
    "p63_concrete_external_order_test_executor_integration_v1"
)
P63_REGISTRY_NAME = "p63_concrete_external_order_test_executor_integration_registry"
STATUS_VALIDATED_REVIEW_ONLY_DISABLED = STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED
STATUS_BLOCKED_FAIL_CLOSED = (
    "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_BLOCKED_FAIL_CLOSED"
)


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
            "p63_concrete_external_order_test_executor_implemented": True,
            "p63_concrete_external_order_test_executor_enabled": False,
            "p63_opaque_credentialed_sender_protocol_implemented": True,
            "p63_opaque_credentialed_sender_injection_enabled": False,
            "p63_concrete_network_sender_included": False,
            "p63_concrete_network_sender_attached": False,
            "p63_external_runtime_network_calls_enabled": False,
            "p63_external_runtime_signing_enabled": False,
            "p63_order_test_endpoint_call_enabled": False,
            "p63_order_test_endpoint_call_performed": False,
            "p63_real_order_submit_enabled": False,
            "p63_real_order_endpoint_called": False,
            "p63_redacted_real_evidence_exported": False,
            "p63_credential_reader_included": False,
            "p63_secret_file_reader_included": False,
            "p63_secret_file_writer_included": False,
            "p63_concrete_signer_included": False,
            "real_order_test_endpoint_call_enabled": False,
            "real_order_test_endpoint_call_performed": False,
            "real_order_endpoint_enabled": False,
            "real_order_endpoint_called": False,
            "real_signed_testnet_evidence_present": False,
            "redacted_real_order_test_evidence_exported": False,
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


def validate_p62_source(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers: list[str] = []
    if payload.get("status") != (
        "P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_VALIDATED_REVIEW_ONLY_DISABLED"
    ):
        blockers.append("P63_P62_STATUS_INVALID")
    if payload.get("blocked") is True:
        blockers.append("P63_P62_SOURCE_BLOCKED")
    for key in (
        "operator_execution_kit_implemented",
        "one_shot_run_guard_implemented",
        "redacted_evidence_exporter_implemented",
        "no_secret_scanner_implemented",
        "p58_bridge_exporter_implemented",
        "external_executor_injection_contract_implemented",
        "no_network_operator_kit_self_test_passed",
        "one_shot_duplicate_run_blocked_in_self_test",
        "redacted_evidence_export_self_test_passed",
        "negative_fixtures_all_blocked",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P63_P62_{key.upper()}_NOT_TRUE")
    for key in (
        "concrete_external_executor_included",
        "credential_reader_included",
        "secret_file_reader_included",
        "secret_file_writer_included",
        "operator_side_external_order_test_execution_kit_enabled",
        "operator_side_external_order_test_execution_enabled",
        "operator_side_external_order_test_network_calls_enabled",
        "operator_side_external_order_test_signing_enabled",
        "operator_side_external_order_test_endpoint_call_enabled",
        "operator_side_external_order_test_endpoint_call_performed",
        "operator_side_external_order_test_real_evidence_exported",
        "real_order_test_endpoint_call_enabled",
        "real_order_test_endpoint_call_performed",
        "real_order_endpoint_enabled",
        "real_order_endpoint_called",
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
            blockers.append(f"P63_P62_{key.upper()}_NOT_FALSE")
    if payload.get("testnet_base_url") != "https://demo-fapi.binance.com":
        blockers.append("P63_P62_TESTNET_BASE_URL_INVALID")
    if payload.get("order_test_path") != "/fapi/v1/order/test":
        blockers.append("P63_P62_ORDER_TEST_PATH_INVALID")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P63_P62_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    validation = {
        "p62_source_valid": not blockers,
        "p62_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "p62_status": payload.get("status"),
        "p62_report_sha256": payload.get(
            "p62_operator_side_external_order_test_execution_kit_sha256"
        ),
    }
    validation["p63_p62_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_p63_concrete_external_order_test_executor_integration_report(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p62 = _read_latest_json(
        cfg, "p62_operator_side_external_order_test_execution_kit_report.json"
    )
    p62_validation = validate_p62_source(p62)
    package_report = build_p63_concrete_executor_package_report()
    blockers = list(p62_validation["p62_source_block_reasons"])
    if package_report.get("status") != STATUS_EXECUTOR_INTEGRATION_VALIDATED_DISABLED:
        blockers.extend(package_report.get("block_reasons", []))
    flags = _execution_false_payload()
    unsafe = truthy_execution_flags({**package_report, **flags})
    if unsafe:
        blockers.append("P63_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    status = STATUS_BLOCKED_FAIL_CLOSED if blockers else STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    report = {
        "artifact_type": "p63_concrete_external_order_test_executor_integration_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p63_version": P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VERSION,
        "p62_source_status": p62.get("status"),
        "p62_source_sha256": p62.get(
            "p62_operator_side_external_order_test_execution_kit_sha256"
        ),
        "p62_source_validation": p62_validation,
        "external_concrete_executor_package_report": package_report,
        "testnet_base_url": "https://demo-fapi.binance.com",
        "order_test_method": "POST",
        "order_test_path": "/fapi/v1/order/test",
        "real_order_submit_path": "/fapi/v1/order",
        "real_order_submit_path_enabled": False,
        "concrete_executor_orchestrator_implemented": True,
        "opaque_credentialed_sender_protocol_implemented": True,
        "metadata_only_credential_reference_enforced": True,
        "external_process_memory_credential_boundary_enforced": True,
        "p61_request_hash_binding_enforced": True,
        "p62_run_hash_binding_enforced": True,
        "one_shot_guard_binding_enforced": True,
        "redacted_result_contract_enforced": True,
        "concrete_network_sender_included": False,
        "credential_reader_included": False,
        "secret_file_reader_included": False,
        "secret_file_writer_included": False,
        "concrete_signer_included": False,
        "no_network_concrete_executor_integration_self_test_passed": package_report[
            "no_network_self_test"
        ]["self_test_passed"],
        "negative_fixtures_all_blocked": package_report["negative_fixture_results"][
            "all_negative_fixtures_blocked_fail_closed"
        ],
        "unsafe_truthy_execution_flags": unsafe,
        **flags,
    }
    report["p63_concrete_external_order_test_executor_integration_sha256"] = sha256_json(
        report
    )
    return report


def persist_p63_concrete_external_order_test_executor_integration(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_p63_concrete_external_order_test_executor_integration_report(cfg=cfg)
    policy = P63ConcreteExecutorPolicy().to_dict()
    manifest = P63ConcreteExecutorPackageManifest().to_dict()
    sender_metadata = P63OpaqueSenderMetadata().to_dict()
    activation = P63ConcreteExecutorActivation().to_dict()
    request = P63ExecutorIntegrationRequest().to_dict()
    self_test = build_p63_no_network_integration_self_test()
    negatives = build_p63_negative_fixture_results()
    summary = {
        "artifact_type": "p63_concrete_external_order_test_executor_integration_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "concrete_executor_orchestrator_implemented": True,
        "opaque_credentialed_sender_protocol_implemented": True,
        "concrete_network_sender_included": False,
        "no_network_self_test_passed": self_test["self_test_passed"],
        "negative_fixtures_all_blocked": negatives[
            "all_negative_fixtures_blocked_fail_closed"
        ],
        "real_order_test_endpoint_call_performed": False,
        "actual_order_submission_performed": False,
        **_execution_false_payload(),
    }
    summary["p63_concrete_external_order_test_executor_integration_summary_sha256"] = sha256_json(
        summary
    )
    registry_record = {
        "artifact_type": "p63_concrete_external_order_test_executor_integration_registry_record",
        "record_id": stable_id(
            "p63_concrete_external_order_test_executor_integration",
            report["p63_concrete_external_order_test_executor_integration_sha256"],
        ),
        "created_at_utc": utc_now_canonical(),
        "status": report["status"],
        "report_sha256": report[
            "p63_concrete_external_order_test_executor_integration_sha256"
        ],
        "review_only": True,
        "runtime_authority_source": False,
        "concrete_executor_orchestrator_implemented": True,
        "concrete_executor_enabled": False,
        "concrete_network_sender_included": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    registry_record[
        "p63_concrete_external_order_test_executor_integration_registry_record_sha256"
    ] = sha256_json(registry_record)
    artifacts = {
        "p63_concrete_external_order_test_executor_integration_report.json": report,
        "p63_concrete_executor_policy_TEMPLATE_DISABLED.json": policy,
        "p63_concrete_executor_package_manifest.json": manifest,
        "p63_opaque_sender_metadata_TEMPLATE_EXTERNAL_ONLY.json": sender_metadata,
        "p63_concrete_executor_activation_TEMPLATE_DISABLED.json": activation,
        "p63_executor_integration_request_TEMPLATE_NO_CALL.json": request,
        "p63_no_network_concrete_executor_integration_self_test_report.json": self_test,
        "p63_concrete_executor_integration_negative_fixture_results.json": negatives,
        "p63_concrete_external_order_test_executor_integration_summary.json": summary,
        "p63_concrete_external_order_test_executor_integration_registry_record.json": registry_record,
    }
    for name, payload in artifacts.items():
        atomic_write_json(latest / name, payload)
    append_registry_record(
        registry_path(cfg, P63_REGISTRY_NAME),
        registry_record,
        registry_name=P63_REGISTRY_NAME,
        id_field="record_id",
    )
    return report
