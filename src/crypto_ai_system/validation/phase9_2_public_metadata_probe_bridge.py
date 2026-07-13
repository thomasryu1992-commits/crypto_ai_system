from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_2_public_metadata_probe_result_filled_validation import (
    _disabled_payload as filled_disabled_payload,
    validate_operator_filled_probe_result,
)
from crypto_ai_system.validation.phase9_2_real_public_metadata_probe_command import (
    COMMAND_FALSE_FLAGS,
    build_phase9_2_real_public_metadata_probe_command_report,
    build_negative_fixture_results as build_command_negative_fixture_results,
)
from crypto_ai_system.validation.phase9_2_real_testnet_endpoint_adapter_preflight import _hash
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _safe_bool

PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_VERSION = "phase9_2_public_metadata_probe_bridge_v1"
PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_REGISTRY_NAME = "phase9_2_public_metadata_probe_bridge_registry"
STATUS_READY = "PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_READY_NO_ORDER_SUBMIT_REVIEW_ONLY"
STATUS_VALIDATED = "PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_VALIDATED_PUBLIC_METADATA_ONLY_NO_ORDER_SUBMIT"
STATUS_BLOCKED = "PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_BLOCKED_FAIL_CLOSED"

SOURCE_TEMPLATE = "phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json"

BRIDGE_FALSE_FLAGS = sorted(set(COMMAND_FALSE_FLAGS + [
    "real_testnet_submit_may_begin",
    "actual_order_submission_performed",
    "real_exchange_endpoint_call_performed",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "api_key_value_read_allowed",
    "api_secret_value_read_allowed",
    "api_key_value_logged",
    "api_secret_value_logged",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "executor_enable_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
]))


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _disabled_payload() -> dict[str, bool]:
    base = {field: False for field in BRIDGE_FALSE_FLAGS}
    base.update(filled_disabled_payload())
    return {key: False for key in base}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    unsafe = [field for field in BRIDGE_FALSE_FLAGS if _safe_bool(data.get(field))]
    nested = data.get("operator_filled_result_payload")
    if isinstance(nested, Mapping):
        unsafe += [field for field in BRIDGE_FALSE_FLAGS if _safe_bool(nested.get(field))]
        op = nested.get("operator_supplied_result")
        if isinstance(op, Mapping):
            unsafe += [field for field in BRIDGE_FALSE_FLAGS if _safe_bool(op.get(field))]
    return sorted(set(unsafe))


def _validate_bridge_inputs(command_result: Mapping[str, Any], operator_payload: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    result = dict(command_result or {})
    if result.get("review_only") is not True:
        errors.append("PHASE9_2_PUBLIC_METADATA_BRIDGE_REQUIRES_COMMAND_RESULT_REVIEW_ONLY_TRUE")
    if result.get("no_order_submit") is not True:
        errors.append("PHASE9_2_PUBLIC_METADATA_BRIDGE_REQUIRES_COMMAND_RESULT_NO_ORDER_SUBMIT_TRUE")
    if result.get("real_testnet_submit_may_begin") is not False:
        errors.append("PHASE9_2_PUBLIC_METADATA_BRIDGE_COMMAND_RESULT_MUST_NOT_ALLOW_SUBMIT")
    unsafe = _unsafe_true_fields(result)
    # public_metadata_network_probe_performed/result_validated may be true in command-result evidence only.
    unsafe = [field for field in unsafe if field not in {"public_metadata_network_probe_performed", "public_metadata_network_probe_result_validated"}]
    if unsafe:
        errors.append("PHASE9_2_PUBLIC_METADATA_BRIDGE_UNSAFE_COMMAND_RESULT_FLAGS:" + ",".join(unsafe))
    if result.get("network_execution_requested") is True and result.get("blocked") is True:
        errors.append("PHASE9_2_PUBLIC_METADATA_BRIDGE_COMMAND_RESULT_BLOCKED")
    if result.get("network_execution_requested") is True and not operator_payload:
        errors.append("PHASE9_2_PUBLIC_METADATA_BRIDGE_EXECUTED_COMMAND_RESULT_MISSING_OPERATOR_PAYLOAD")
    return not errors, errors


def bridge_public_metadata_probe_result(
    *,
    cfg: AppConfig | None = None,
    execute_network: bool = False,
    fetcher: Callable[[str, int], tuple[int, str]] | None = None,
    created_at_utc: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    command_report, command_template, command_validation, command_result = build_phase9_2_real_public_metadata_probe_command_report(
        cfg=cfg,
        execute_network=execute_network,
        fetcher=fetcher,
        created_at_utc=created_at_utc,
    )
    operator_payload_raw = command_result.get("operator_filled_result_payload") if isinstance(command_result, Mapping) else None
    operator_payload = dict(operator_payload_raw) if isinstance(operator_payload_raw, Mapping) else None
    input_ok, input_blockers = _validate_bridge_inputs(command_result, operator_payload)
    source_template = _read_latest_json(cfg, SOURCE_TEMPLATE)
    validation: dict[str, Any] | None = None
    validation_blockers: list[str] = []
    if operator_payload:
        validation = validate_operator_filled_probe_result(operator_payload, source_template=source_template or None)
        validation_blockers = list(validation.get("block_reasons", []))
    blockers = list(command_report.get("block_reasons", [])) + list(command_validation.get("block_reasons", [])) + input_blockers + validation_blockers
    validated = bool(execute_network and operator_payload and validation and not blockers and validation.get("operator_filled_public_metadata_probe_result_validated"))
    report_id = stable_id("phase9_2_public_metadata_probe_bridge", {
        "command_report_sha256": _hash(command_report),
        "command_result_sha256": _hash({k: v for k, v in command_result.items() if k != "operator_filled_result_payload"}) if isinstance(command_result, Mapping) else "",
        "operator_payload_sha256": _hash(operator_payload or {}),
        "execute_network": execute_network,
        "version": PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_VERSION,
    }, 24)
    report = {
        "artifact_type": "phase9_2_public_metadata_probe_bridge_report",
        "phase9_2_public_metadata_probe_bridge_id": report_id,
        "phase9_2_public_metadata_probe_bridge_version": PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_VERSION,
        "status": STATUS_BLOCKED if blockers else (STATUS_VALIDATED if validated else STATUS_READY),
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "no_order_submit": True,
        "public_metadata_only": True,
        "network_execution_requested": bool(execute_network),
        "command_report_status": command_report.get("status"),
        "command_template_created": bool(command_template),
        "command_template_valid": bool(command_template and not command_validation.get("blocked")),
        "command_result_status": command_result.get("status") if isinstance(command_result, Mapping) else None,
        "public_metadata_network_probe_command_ready": bool(command_report.get("public_metadata_network_probe_command_ready")),
        "public_metadata_network_probe_performed_by_command": bool(command_result.get("public_metadata_network_probe_performed")) if isinstance(command_result, Mapping) else False,
        "operator_filled_result_payload_created": bool(operator_payload),
        "operator_filled_result_written": bool(validated),
        "filled_validation_executed": bool(validation),
        "operator_filled_public_metadata_probe_result_validated": bool(validated),
        "public_metadata_network_probe_result_validated": bool(validated),
        "real_testnet_metadata_conditions_ready_for_submit_review_only": bool(validated),
        "real_testnet_submit_may_begin": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "private_account_endpoint_called": False,
        "balance_endpoint_called": False,
        "position_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "next_action_if_validated": "separate_explicit_one_order_runtime_submit_approval_review_only_not_automatic",
        "block_reasons": blockers,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    # Do not expose public metadata probe success as execution authority. The bridge report keeps
    # submit and endpoint-order flags false even when public metadata validation succeeds.
    report["real_testnet_metadata_conditions_ready_for_submit_review_only"] = bool(validated)
    report["operator_filled_public_metadata_probe_result_validated"] = bool(validated)
    report["public_metadata_network_probe_result_validated"] = bool(validated)
    report["public_metadata_network_probe_performed_by_command"] = bool(command_result.get("public_metadata_network_probe_performed")) if isinstance(command_result, Mapping) else False
    report["phase9_2_public_metadata_probe_bridge_report_sha256"] = sha256_json(report)
    return report, {k: v for k, v in command_result.items() if k != "operator_filled_result_payload"}, operator_payload, validation


def persist_phase9_2_public_metadata_probe_bridge(
    *,
    cfg: AppConfig | None = None,
    execute_network: bool = False,
    fetcher: Callable[[str, int], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, command_result, operator_payload, validation = bridge_public_metadata_probe_result(
        cfg=cfg,
        execute_network=execute_network,
        fetcher=fetcher,
    )
    negative = build_negative_fixture_results()
    files: dict[str, Mapping[str, Any]] = {
        "phase9_2_public_metadata_probe_bridge_report.json": report,
        "phase9_2_public_metadata_probe_bridge_command_result.json": command_result,
        "phase9_2_public_metadata_probe_bridge_negative_fixture_results.json": negative,
    }
    if operator_payload and report.get("operator_filled_result_written") is True:
        files["phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_REVIEW_ONLY.json"] = operator_payload
    if validation:
        files["phase9_2_public_metadata_probe_bridge_filled_validation_report.json"] = validation
        if report.get("operator_filled_result_written") is True:
            files["phase9_2_public_metadata_probe_result_filled_validation_payload_validation_report.json"] = validation
    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)
    handoff = "\n".join([
        "# Phase 9.2 Public Metadata Probe Bridge / No Order Submit",
        "",
        "This bridge runs or inspects the real public metadata probe command result and, when an explicitly requested public-only probe creates a valid redacted payload, writes it into the filled-validation input path.",
        "It never submits orders, calls private endpoints, creates signatures, reads secrets, or enables executors.",
        "A valid public metadata bridge result is evidence only and does not grant runtime submit authority.",
    ])
    (latest / "PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")
    record = append_registry_record(
        registry_path(cfg, PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_public_metadata_probe_bridge_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_order_submit": True,
            "network_execution_requested": report["network_execution_requested"],
            "sha256": report["phase9_2_public_metadata_probe_bridge_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_REGISTRY_NAME,
        id_field="phase9_2_public_metadata_probe_bridge_registry_id",
        hash_field="phase9_2_public_metadata_probe_bridge_registry_record_sha256",
        id_prefix="phase9_2_public_metadata_probe_bridge_registry",
    )
    atomic_write_json(latest / "phase9_2_public_metadata_probe_bridge_registry_record.json", record)
    return report


def build_negative_fixture_results() -> dict[str, Any]:
    fixtures = {
        "order_endpoint_called_true": {"review_only": True, "no_order_submit": True, "real_testnet_submit_may_begin": False, "order_endpoint_called": True},
        "submit_allowed_true": {"review_only": True, "no_order_submit": True, "real_testnet_submit_may_begin": True},
        "signature_created_true": {"review_only": True, "no_order_submit": True, "real_testnet_submit_may_begin": False, "signature_created": True},
        "private_account_endpoint_called_true": {"review_only": True, "no_order_submit": True, "real_testnet_submit_may_begin": False, "private_account_endpoint_called": True},
    }
    results: dict[str, Any] = {}
    for name, command_result in fixtures.items():
        _ok, reasons = _validate_bridge_inputs(command_result, None)
        results[name] = {"fixture_name": name, "blocked": bool(reasons), "fail_closed": bool(reasons), "block_reasons": reasons}
    output = {
        "artifact_type": "phase9_2_public_metadata_probe_bridge_negative_fixture_results",
        "review_only": True,
        "no_order_submit": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_public_metadata_probe_bridge_negative_fixture_results_sha256"] = sha256_json(output)
    return output
