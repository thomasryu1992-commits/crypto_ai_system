from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from external_runtime_packages.binance_futures_testnet_adapter import (
    P61ExternalExecutorMetadata,
    P61ExternalRuntimeActivation,
    P61OperatorOrderTestApproval,
    P61OrderTestAdapterPolicy,
    P61OrderTestRequestDescriptor,
    STATUS_ADAPTER_VALIDATED_DISABLED,
    build_p61_adapter_package_report,
    build_p61_negative_fixture_results,
    build_p61_no_network_self_test,
)

P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_VERSION = (
    "p61_real_testnet_order_test_dry_validation_adapter_v1"
)
P61_REGISTRY_NAME = "p61_real_testnet_order_test_dry_validation_adapter_registry"
STATUS_VALIDATED_REVIEW_ONLY_DISABLED = STATUS_ADAPTER_VALIDATED_DISABLED
STATUS_BLOCKED_FAIL_CLOSED = (
    "P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_BLOCKED_FAIL_CLOSED"
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
            "real_testnet_order_test_adapter_implemented": True,
            "approved_external_runtime_order_test_path_implemented": True,
            "external_signed_order_test_executor_protocol_implemented": True,
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
            "external_runtime_raw_request_persistence_enabled": False,
            "external_runtime_raw_response_persistence_enabled": False,
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


def validate_p60_source(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers: list[str] = []
    if payload.get("status") != (
        "P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VALIDATED_REVIEW_ONLY_DISABLED"
    ):
        blockers.append("P61_P60_STATUS_INVALID")
    if payload.get("blocked") is True:
        blockers.append("P61_P60_SOURCE_BLOCKED")
    for key in (
        "external_signer_transport_harness_implemented",
        "external_signer_injection_harness_implemented",
        "external_http_transport_injection_harness_implemented",
        "order_test_endpoint_dry_validation_implemented",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P61_P60_{key.upper()}_NOT_TRUE")
    for key in (
        "external_signer_transport_harness_enabled",
        "external_signer_injection_enabled",
        "external_http_transport_injection_enabled",
        "real_order_test_endpoint_call_enabled",
        "real_order_endpoint_enabled",
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
            blockers.append(f"P61_P60_{key.upper()}_NOT_FALSE")
    if payload.get("order_test_endpoint_path") != "/fapi/v1/order/test":
        blockers.append("P61_P60_ORDER_TEST_ENDPOINT_PATH_INVALID")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P61_P60_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    validation = {
        "p60_source_valid": not blockers,
        "p60_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "p60_status": payload.get("status"),
        "p60_report_sha256": payload.get(
            "p60_external_signer_http_transport_injection_harness_sha256"
        ),
    }
    validation["p61_p60_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_p61_real_testnet_order_test_dry_validation_adapter_report(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p60 = _read_latest_json(
        cfg, "p60_external_signer_http_transport_injection_harness_report.json"
    )
    p60_validation = validate_p60_source(p60)
    package_report = build_p61_adapter_package_report()
    blockers = list(p60_validation["p60_source_block_reasons"])
    if package_report.get("status") != STATUS_ADAPTER_VALIDATED_DISABLED:
        blockers.extend(package_report.get("block_reasons", []))
    flags = _execution_false_payload()
    unsafe = truthy_execution_flags({**package_report, **flags})
    if unsafe:
        blockers.append("P61_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    status = STATUS_BLOCKED_FAIL_CLOSED if blockers else STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    report = {
        "artifact_type": "p61_real_testnet_order_test_dry_validation_adapter_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p61_version": P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_VERSION,
        "p60_source_status": p60.get("status"),
        "p60_source_sha256": p60.get(
            "p60_external_signer_http_transport_injection_harness_sha256"
        ),
        "p60_source_validation": p60_validation,
        "external_adapter_package_report": package_report,
        "testnet_base_url": "https://demo-fapi.binance.com",
        "order_test_method": "POST",
        "order_test_path": "/fapi/v1/order/test",
        "real_order_submit_path": "/fapi/v1/order",
        "real_order_submit_path_enabled": False,
        "real_order_test_adapter_implemented": True,
        "approved_external_runtime_order_test_path_implemented": True,
        "external_signed_order_test_executor_protocol_implemented": True,
        "metadata_only_credential_reference_enforced": True,
        "external_process_memory_credential_boundary_enforced": True,
        "redacted_response_contract_enforced": True,
        "concrete_external_executor_included": False,
        "credential_reader_included": False,
        "no_network_injected_executor_self_test_passed": package_report[
            "no_network_self_test"
        ]["self_test_passed"],
        "negative_fixtures_all_blocked": package_report[
            "negative_fixture_results"
        ]["all_negative_fixtures_blocked_fail_closed"],
        "unsafe_truthy_execution_flags": unsafe,
        **flags,
    }
    report["p61_real_testnet_order_test_dry_validation_adapter_sha256"] = sha256_json(report)
    return report


def persist_p61_real_testnet_order_test_dry_validation_adapter(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_p61_real_testnet_order_test_dry_validation_adapter_report(cfg=cfg)
    policy = P61OrderTestAdapterPolicy().to_dict()
    executor_metadata = P61ExternalExecutorMetadata().to_dict()
    approval_template = P61OperatorOrderTestApproval().to_dict()
    request_template = P61OrderTestRequestDescriptor().to_dict()
    activation_template = P61ExternalRuntimeActivation().to_dict()
    self_test = build_p61_no_network_self_test()
    negatives = build_p61_negative_fixture_results()
    summary = {
        "artifact_type": "p61_real_testnet_order_test_dry_validation_adapter_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "real_order_test_adapter_implemented": True,
        "approved_external_runtime_order_test_path_implemented": True,
        "order_test_path": "/fapi/v1/order/test",
        "real_order_submit_path_enabled": False,
        "no_network_injected_executor_self_test_passed": self_test["self_test_passed"],
        "negative_fixtures_all_blocked": negatives[
            "all_negative_fixtures_blocked_fail_closed"
        ],
        **_execution_false_payload(),
    }
    summary["p61_real_testnet_order_test_dry_validation_adapter_summary_sha256"] = sha256_json(
        summary
    )
    registry_record = {
        "artifact_type": "p61_real_testnet_order_test_dry_validation_adapter_registry_record",
        "record_id": stable_id(
            "p61_real_testnet_order_test_dry_validation_adapter",
            report["p61_real_testnet_order_test_dry_validation_adapter_sha256"],
        ),
        "created_at_utc": utc_now_canonical(),
        "status": report["status"],
        "report_sha256": report[
            "p61_real_testnet_order_test_dry_validation_adapter_sha256"
        ],
        "review_only": True,
        "runtime_authority_source": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    registry_record[
        "p61_real_testnet_order_test_dry_validation_adapter_registry_record_sha256"
    ] = sha256_json(registry_record)
    artifacts = {
        "p61_real_testnet_order_test_dry_validation_adapter_report.json": report,
        "p61_order_test_adapter_policy_TEMPLATE_DISABLED.json": policy,
        "p61_external_signed_order_test_executor_metadata_TEMPLATE.json": executor_metadata,
        "p61_operator_order_test_approval_TEMPLATE_NO_CALL.json": approval_template,
        "p61_order_test_request_descriptor_TEMPLATE_NO_CALL.json": request_template,
        "p61_external_runtime_activation_TEMPLATE_DISABLED.json": activation_template,
        "p61_order_test_no_network_injected_executor_self_test_report.json": self_test,
        "p61_real_order_test_adapter_negative_fixture_results.json": negatives,
        "p61_real_testnet_order_test_dry_validation_adapter_summary.json": summary,
        "p61_real_testnet_order_test_dry_validation_adapter_registry_record.json": registry_record,
    }
    for name, payload in artifacts.items():
        atomic_write_json(latest / name, payload)
    append_registry_record(
        registry_path(cfg, P61_REGISTRY_NAME),
        registry_record,
        registry_name=P61_REGISTRY_NAME,
        id_field="record_id",
    )
    return report
