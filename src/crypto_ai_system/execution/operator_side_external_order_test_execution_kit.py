from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.external_adapter_review_contracts import (
    P62EvidenceExportPolicy,
    P62OperatorExecutionActivation,
    P62OperatorExecutionKitManifest,
    P62OperatorExecutionKitPolicy,
    P62OperatorRunRequest,
    STATUS_KIT_VALIDATED_DISABLED,
    build_p62_negative_fixture_results,
    build_p62_no_network_self_test,
    build_p62_operator_execution_kit_package_report,
)
from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
    truthy_execution_flags,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_VERSION = (
    "p62_operator_side_external_order_test_execution_kit_v1"
)
P62_REGISTRY_NAME = "p62_operator_side_external_order_test_execution_kit_registry"
STATUS_VALIDATED_REVIEW_ONLY_DISABLED = STATUS_KIT_VALIDATED_DISABLED
STATUS_BLOCKED_FAIL_CLOSED = (
    "P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_BLOCKED_FAIL_CLOSED"
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
            "operator_side_external_order_test_execution_kit_implemented": True,
            "operator_side_external_order_test_execution_kit_enabled": False,
            "operator_side_external_order_test_execution_enabled": False,
            "operator_side_external_order_test_network_calls_enabled": False,
            "operator_side_external_order_test_signing_enabled": False,
            "operator_side_external_order_test_endpoint_call_enabled": False,
            "operator_side_external_order_test_endpoint_call_performed": False,
            "operator_side_external_order_test_one_shot_guard_acquired": False,
            "operator_side_external_order_test_evidence_exported": False,
            "operator_side_external_order_test_real_evidence_exported": False,
            "operator_side_external_order_test_concrete_executor_included": False,
            "operator_side_external_order_test_credential_reader_included": False,
            "operator_side_external_order_test_secret_file_reader_included": False,
            "operator_side_external_order_test_secret_file_writer_included": False,
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


def validate_p61_source(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers: list[str] = []
    if payload.get("status") != (
        "P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_VALIDATED_REVIEW_ONLY_DISABLED"
    ):
        blockers.append("P62_P61_STATUS_INVALID")
    if payload.get("blocked") is True:
        blockers.append("P62_P61_SOURCE_BLOCKED")
    for key in (
        "real_order_test_adapter_implemented",
        "approved_external_runtime_order_test_path_implemented",
        "external_signed_order_test_executor_protocol_implemented",
        "metadata_only_credential_reference_enforced",
        "external_process_memory_credential_boundary_enforced",
        "redacted_response_contract_enforced",
        "no_network_injected_executor_self_test_passed",
        "negative_fixtures_all_blocked",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P62_P61_{key.upper()}_NOT_TRUE")
    for key in (
        "external_runtime_order_test_adapter_enabled",
        "external_runtime_order_test_signer_injection_enabled",
        "external_runtime_order_test_transport_injection_enabled",
        "external_runtime_order_test_network_calls_enabled",
        "external_runtime_order_test_signing_enabled",
        "real_order_test_endpoint_call_enabled",
        "real_order_test_endpoint_call_performed",
        "real_order_endpoint_enabled",
        "real_order_endpoint_called",
        "external_runtime_concrete_order_test_executor_included",
        "external_runtime_credential_reader_included",
        "real_signed_testnet_evidence_present",
        "redacted_real_order_test_evidence_exported",
        "actual_p7_import_ready",
        "actual_order_submission_performed",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
        "runtime_mutation_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P62_P61_{key.upper()}_NOT_FALSE")
    if payload.get("testnet_base_url") != "https://demo-fapi.binance.com":
        blockers.append("P62_P61_TESTNET_BASE_URL_INVALID")
    if payload.get("order_test_path") != "/fapi/v1/order/test":
        blockers.append("P62_P61_ORDER_TEST_PATH_INVALID")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P62_P61_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    validation = {
        "p61_source_valid": not blockers,
        "p61_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "p61_status": payload.get("status"),
        "p61_report_sha256": payload.get(
            "p61_real_testnet_order_test_dry_validation_adapter_sha256"
        ),
    }
    validation["p62_p61_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_p62_operator_side_external_order_test_execution_kit_report(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p61 = _read_latest_json(
        cfg, "p61_real_testnet_order_test_dry_validation_adapter_report.json"
    )
    p61_validation = validate_p61_source(p61)
    package_report = build_p62_operator_execution_kit_package_report()
    blockers = list(p61_validation["p61_source_block_reasons"])
    if package_report.get("status") != STATUS_KIT_VALIDATED_DISABLED:
        blockers.extend(package_report.get("block_reasons", []))
    flags = _execution_false_payload()
    unsafe = truthy_execution_flags({**package_report, **flags})
    if unsafe:
        blockers.append("P62_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    status = STATUS_BLOCKED_FAIL_CLOSED if blockers else STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    report = {
        "artifact_type": "p62_operator_side_external_order_test_execution_kit_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p62_version": P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_VERSION,
        "p61_source_status": p61.get("status"),
        "p61_source_sha256": p61.get(
            "p61_real_testnet_order_test_dry_validation_adapter_sha256"
        ),
        "p61_source_validation": p61_validation,
        "external_operator_execution_kit_package_report": package_report,
        "testnet_base_url": "https://demo-fapi.binance.com",
        "order_test_method": "POST",
        "order_test_path": "/fapi/v1/order/test",
        "real_order_submit_path": "/fapi/v1/order",
        "real_order_submit_path_enabled": False,
        "operator_execution_kit_implemented": True,
        "one_shot_run_guard_implemented": True,
        "redacted_evidence_exporter_implemented": True,
        "no_secret_scanner_implemented": True,
        "p58_bridge_exporter_implemented": True,
        "external_executor_injection_contract_implemented": True,
        "concrete_external_executor_included": False,
        "credential_reader_included": False,
        "secret_file_reader_included": False,
        "secret_file_writer_included": False,
        "no_network_operator_kit_self_test_passed": package_report["no_network_self_test"][
            "self_test_passed"
        ],
        "one_shot_duplicate_run_blocked_in_self_test": package_report["no_network_self_test"][
            "duplicate_second_run_blocked"
        ],
        "redacted_evidence_export_self_test_passed": package_report[
            "no_network_self_test"
        ]["redacted_evidence_export_completed"],
        "negative_fixtures_all_blocked": package_report["negative_fixture_results"][
            "all_negative_fixtures_blocked_fail_closed"
        ],
        "unsafe_truthy_execution_flags": unsafe,
        **flags,
    }
    report["p62_operator_side_external_order_test_execution_kit_sha256"] = sha256_json(
        report
    )
    return report


def persist_p62_operator_side_external_order_test_execution_kit(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_p62_operator_side_external_order_test_execution_kit_report(cfg=cfg)
    policy = P62OperatorExecutionKitPolicy().to_dict()
    manifest = P62OperatorExecutionKitManifest().to_dict()
    run_template = P62OperatorRunRequest().to_dict()
    activation_template = P62OperatorExecutionActivation().to_dict()
    export_policy = P62EvidenceExportPolicy().to_dict()
    self_test = build_p62_no_network_self_test()
    negatives = build_p62_negative_fixture_results()
    summary = {
        "artifact_type": "p62_operator_side_external_order_test_execution_kit_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "operator_execution_kit_implemented": True,
        "one_shot_run_guard_implemented": True,
        "redacted_evidence_exporter_implemented": True,
        "no_network_operator_kit_self_test_passed": self_test["self_test_passed"],
        "negative_fixtures_all_blocked": negatives[
            "all_negative_fixtures_blocked_fail_closed"
        ],
        "real_order_test_endpoint_call_performed": False,
        "actual_order_submission_performed": False,
        **_execution_false_payload(),
    }
    summary["p62_operator_side_external_order_test_execution_kit_summary_sha256"] = sha256_json(
        summary
    )
    registry_record = {
        "artifact_type": "p62_operator_side_external_order_test_execution_kit_registry_record",
        "record_id": stable_id(
            "p62_operator_side_external_order_test_execution_kit",
            report["p62_operator_side_external_order_test_execution_kit_sha256"],
        ),
        "created_at_utc": utc_now_canonical(),
        "status": report["status"],
        "report_sha256": report[
            "p62_operator_side_external_order_test_execution_kit_sha256"
        ],
        "review_only": True,
        "runtime_authority_source": False,
        "operator_execution_kit_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    registry_record[
        "p62_operator_side_external_order_test_execution_kit_registry_record_sha256"
    ] = sha256_json(registry_record)
    artifacts = {
        "p62_operator_side_external_order_test_execution_kit_report.json": report,
        "p62_operator_execution_kit_policy_TEMPLATE_DISABLED.json": policy,
        "p62_operator_execution_kit_manifest.json": manifest,
        "p62_operator_run_request_TEMPLATE_NO_CALL.json": run_template,
        "p62_operator_execution_activation_TEMPLATE_DISABLED.json": activation_template,
        "p62_evidence_export_policy.json": export_policy,
        "p62_operator_execution_kit_no_network_self_test_report.json": self_test,
        "p62_operator_execution_kit_negative_fixture_results.json": negatives,
        "p62_operator_side_external_order_test_execution_kit_summary.json": summary,
        "p62_operator_side_external_order_test_execution_kit_registry_record.json": registry_record,
    }
    for name, payload in artifacts.items():
        atomic_write_json(latest / name, payload)
    append_registry_record(
        registry_path(cfg, P62_REGISTRY_NAME),
        registry_record,
        registry_name=P62_REGISTRY_NAME,
        id_field="record_id",
    )
    return report
