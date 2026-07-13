from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.external_adapter_review_contracts import (
    P64SubprocessBridgeActivation,
    P64SubprocessBridgePackageManifest,
    P64SubprocessBridgePolicy,
    P64SubprocessBridgeRequest,
    P64SubprocessSenderMetadata,
    STATUS_BRIDGE_VALIDATED_DISABLED,
    build_p64_negative_fixture_results,
    build_p64_no_network_subprocess_bridge_self_test,
    build_p64_subprocess_bridge_package_report,
)
from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
    truthy_execution_flags,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_INTEGRATION_VERSION = (
    "p64_opaque_sender_subprocess_bridge_integration_v1"
)
P64_REGISTRY_NAME = "p64_opaque_sender_subprocess_bridge_registry"
STATUS_VALIDATED_REVIEW_ONLY_DISABLED = STATUS_BRIDGE_VALIDATED_DISABLED
STATUS_BLOCKED_FAIL_CLOSED = "P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_BLOCKED_FAIL_CLOSED"


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
            "p64_opaque_sender_subprocess_bridge_implemented": True,
            "p64_opaque_sender_subprocess_bridge_enabled": False,
            "p64_subprocess_execution_enabled": False,
            "p64_sender_program_injection_enabled": False,
            "p64_concrete_network_sender_program_included": False,
            "p64_concrete_network_sender_program_attached": False,
            "p64_external_runtime_network_calls_enabled": False,
            "p64_external_runtime_signing_enabled": False,
            "p64_order_test_endpoint_call_enabled": False,
            "p64_order_test_endpoint_call_performed": False,
            "p64_real_order_submit_enabled": False,
            "p64_real_order_endpoint_called": False,
            "p64_redacted_real_evidence_exported": False,
            "p64_credential_reader_included": False,
            "p64_secret_file_reader_included": False,
            "p64_secret_file_writer_included": False,
            "p64_shell_execution_enabled": False,
            "p64_inherited_environment_enabled": False,
            "p64_raw_request_persistence_enabled": False,
            "p64_raw_response_persistence_enabled": False,
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


def validate_p63_source(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers: list[str] = []
    if payload.get("status") != (
        "P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VALIDATED_REVIEW_ONLY_DISABLED"
    ):
        blockers.append("P64_P63_STATUS_INVALID")
    if payload.get("blocked") is True:
        blockers.append("P64_P63_SOURCE_BLOCKED")
    for key in (
        "concrete_executor_orchestrator_implemented",
        "opaque_credentialed_sender_protocol_implemented",
        "metadata_only_credential_reference_enforced",
        "external_process_memory_credential_boundary_enforced",
        "p61_request_hash_binding_enforced",
        "p62_run_hash_binding_enforced",
        "one_shot_guard_binding_enforced",
        "redacted_result_contract_enforced",
        "no_network_concrete_executor_integration_self_test_passed",
        "negative_fixtures_all_blocked",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P64_P63_{key.upper()}_NOT_TRUE")
    for key in (
        "concrete_network_sender_included",
        "credential_reader_included",
        "secret_file_reader_included",
        "secret_file_writer_included",
        "concrete_signer_included",
        "p63_concrete_external_order_test_executor_enabled",
        "p63_opaque_credentialed_sender_injection_enabled",
        "p63_external_runtime_network_calls_enabled",
        "p63_external_runtime_signing_enabled",
        "p63_order_test_endpoint_call_enabled",
        "p63_order_test_endpoint_call_performed",
        "p63_real_order_submit_enabled",
        "p63_real_order_endpoint_called",
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
            blockers.append(f"P64_P63_{key.upper()}_NOT_FALSE")
    if payload.get("testnet_base_url") != "https://demo-fapi.binance.com":
        blockers.append("P64_P63_TESTNET_BASE_URL_INVALID")
    if payload.get("order_test_path") != "/fapi/v1/order/test":
        blockers.append("P64_P63_ORDER_TEST_PATH_INVALID")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P64_P63_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    validation = {
        "p63_source_valid": not blockers,
        "p63_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "p63_status": payload.get("status"),
        "p63_report_sha256": payload.get(
            "p63_concrete_external_order_test_executor_integration_sha256"
        ),
    }
    validation["p64_p63_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_p64_opaque_sender_subprocess_bridge_report(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p63 = _read_latest_json(
        cfg, "p63_concrete_external_order_test_executor_integration_report.json"
    )
    p63_validation = validate_p63_source(p63)
    package_report = build_p64_subprocess_bridge_package_report()
    blockers = list(p63_validation["p63_source_block_reasons"])
    if package_report.get("status") != STATUS_BRIDGE_VALIDATED_DISABLED:
        blockers.extend(package_report.get("block_reasons", []))
    flags = _execution_false_payload()
    unsafe = truthy_execution_flags({**package_report, **flags})
    if unsafe:
        blockers.append("P64_UNSAFE_TRUTHY_EXECUTION_FLAGS:" + ",".join(unsafe))
    status = STATUS_BLOCKED_FAIL_CLOSED if blockers else STATUS_VALIDATED_REVIEW_ONLY_DISABLED
    report = {
        "artifact_type": "p64_opaque_sender_subprocess_bridge_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "p64_version": P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_INTEGRATION_VERSION,
        "p63_source_status": p63.get("status"),
        "p63_source_sha256": p63.get(
            "p63_concrete_external_order_test_executor_integration_sha256"
        ),
        "p63_source_validation": p63_validation,
        "external_subprocess_bridge_package_report": package_report,
        "testnet_base_url": "https://demo-fapi.binance.com",
        "order_test_method": "POST",
        "order_test_path": "/fapi/v1/order/test",
        "real_order_submit_path": "/fapi/v1/order",
        "real_order_submit_path_enabled": False,
        "opaque_sender_subprocess_bridge_implemented": True,
        "metadata_only_request_file_implemented": True,
        "executable_hash_attestation_implemented": True,
        "launcher_hash_attestation_implemented": True,
        "minimal_environment_allowlist_implemented": True,
        "shell_disabled": True,
        "stdin_disabled": True,
        "timeout_guard_implemented": True,
        "output_size_guard_implemented": True,
        "redacted_json_stdout_contract_enforced": True,
        "ephemeral_request_file_deleted_after_run": True,
        "concrete_network_sender_program_included": False,
        "credential_reader_included": False,
        "secret_file_reader_included": False,
        "secret_file_writer_included": False,
        "no_network_subprocess_bridge_self_test_passed": package_report[
            "no_network_self_test"
        ]["self_test_passed"],
        "negative_fixtures_all_blocked": package_report["negative_fixture_results"][
            "all_negative_fixtures_blocked_fail_closed"
        ],
        "unsafe_truthy_execution_flags": unsafe,
        **flags,
    }
    report["p64_opaque_sender_subprocess_bridge_sha256"] = sha256_json(report)
    return report


def persist_p64_opaque_sender_subprocess_bridge(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_p64_opaque_sender_subprocess_bridge_report(cfg=cfg)
    policy = P64SubprocessBridgePolicy().to_dict()
    manifest = P64SubprocessBridgePackageManifest().to_dict()
    sender_metadata = P64SubprocessSenderMetadata().to_dict()
    activation = P64SubprocessBridgeActivation().to_dict()
    request = P64SubprocessBridgeRequest().to_dict()
    self_test = build_p64_no_network_subprocess_bridge_self_test()
    negatives = build_p64_negative_fixture_results()
    summary = {
        "artifact_type": "p64_opaque_sender_subprocess_bridge_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "opaque_sender_subprocess_bridge_implemented": True,
        "metadata_only_request_file_implemented": True,
        "executable_hash_attestation_implemented": True,
        "minimal_environment_allowlist_implemented": True,
        "shell_disabled": True,
        "stdin_disabled": True,
        "concrete_network_sender_program_included": False,
        "no_network_self_test_passed": self_test["self_test_passed"],
        "negative_fixtures_all_blocked": negatives[
            "all_negative_fixtures_blocked_fail_closed"
        ],
        "real_order_test_endpoint_call_performed": False,
        "actual_order_submission_performed": False,
        **_execution_false_payload(),
    }
    summary["p64_opaque_sender_subprocess_bridge_summary_sha256"] = sha256_json(summary)
    registry_record = {
        "artifact_type": "p64_opaque_sender_subprocess_bridge_registry_record",
        "record_id": stable_id(
            "p64_opaque_sender_subprocess_bridge",
            report["p64_opaque_sender_subprocess_bridge_sha256"],
        ),
        "created_at_utc": utc_now_canonical(),
        "status": report["status"],
        "report_sha256": report["p64_opaque_sender_subprocess_bridge_sha256"],
        "review_only": True,
        "runtime_authority_source": False,
        "subprocess_bridge_implemented": True,
        "subprocess_bridge_enabled": False,
        "concrete_network_sender_program_included": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    registry_record["p64_opaque_sender_subprocess_bridge_registry_record_sha256"] = sha256_json(
        registry_record
    )
    artifacts = {
        "p64_opaque_sender_subprocess_bridge_report.json": report,
        "p64_subprocess_bridge_policy_TEMPLATE_DISABLED.json": policy,
        "p64_subprocess_bridge_package_manifest.json": manifest,
        "p64_subprocess_sender_metadata_TEMPLATE_EXTERNAL_ONLY.json": sender_metadata,
        "p64_subprocess_bridge_activation_TEMPLATE_DISABLED.json": activation,
        "p64_subprocess_bridge_request_TEMPLATE_NO_CALL.json": request,
        "p64_no_network_subprocess_bridge_self_test_report.json": self_test,
        "p64_subprocess_bridge_negative_fixture_results.json": negatives,
        "p64_opaque_sender_subprocess_bridge_summary.json": summary,
        "p64_opaque_sender_subprocess_bridge_registry_record.json": registry_record,
    }
    for name, payload in artifacts.items():
        atomic_write_json(latest / name, payload)
    append_registry_record(
        registry_path(cfg, P64_REGISTRY_NAME),
        registry_record,
        registry_name=P64_REGISTRY_NAME,
        id_field="record_id",
    )
    return report
