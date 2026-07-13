from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_2_public_metadata_network_dry_probe_result_intake import (
    PHASE9_2_PUBLIC_METADATA_NETWORK_DRY_PROBE_RESULT_INTAKE_VERSION,
    RESULT_FALSE_FLAGS,
    REQUIRED_RESULT_FIELDS,
    validate_public_metadata_probe_result_payload,
)
from crypto_ai_system.validation.phase9_2_real_testnet_endpoint_adapter_preflight import _hash
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _safe_bool

PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_VERSION = "phase9_2_public_metadata_probe_result_filled_validation_v1"
PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_REGISTRY_NAME = "phase9_2_public_metadata_probe_result_filled_validation_registry"
STATUS_READY = "PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_READY_NO_ORDER_SUBMIT_REVIEW_ONLY"
STATUS_VALIDATED = "PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATED_NO_ORDER_SUBMIT_REVIEW_ONLY"
STATUS_AWAITING = "PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_AWAITING_OPERATOR_FILLED_RESULT_REVIEW_ONLY"
STATUS_BLOCKED = "PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_BLOCKED_FAIL_CLOSED"

SOURCE_INTAKE_REPORT = "phase9_2_public_metadata_network_dry_probe_result_intake_report.json"
SOURCE_TEMPLATE = "phase9_2_public_metadata_network_dry_probe_RESULT_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json"
FILLED_RESULT_CANDIDATES = [
    "phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_REVIEW_ONLY.json",
    "phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_NO_ORDER_SUBMIT_REVIEW_ONLY.json",
]

FALSE_FLAGS = sorted(set(RESULT_FALSE_FLAGS + [
    "real_testnet_submit_may_begin",
    "actual_order_submission_performed",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
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


def _disabled_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _find_filled_result(cfg: AppConfig) -> tuple[str | None, dict[str, Any]]:
    latest = _latest_dir(cfg)
    for name in FILLED_RESULT_CANDIDATES:
        payload = read_json(latest / name, default={})
        if isinstance(payload, Mapping) and payload:
            return name, dict(payload)
    return None, {}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return sorted(field for field in FALSE_FLAGS if _safe_bool(data.get(field)))


def _source_ready(intake: Mapping[str, Any], template: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not intake:
        blockers.append("PHASE9_2_FILLED_METADATA_VALIDATION_SOURCE_INTAKE_REPORT_MISSING")
    else:
        if intake.get("blocked") is True or intake.get("fail_closed") is True:
            blockers.append("PHASE9_2_FILLED_METADATA_VALIDATION_SOURCE_INTAKE_BLOCKED")
        if intake.get("public_metadata_network_probe_result_intake_ready") is not True:
            blockers.append("PHASE9_2_FILLED_METADATA_VALIDATION_REQUIRES_INTAKE_READY")
        if intake.get("real_testnet_submit_may_begin") is not False:
            blockers.append("PHASE9_2_FILLED_METADATA_VALIDATION_SOURCE_MUST_NOT_ALLOW_SUBMIT")
    if not template:
        blockers.append("PHASE9_2_FILLED_METADATA_VALIDATION_SOURCE_TEMPLATE_MISSING")
    else:
        if template.get("review_only") is not True or template.get("no_order_submit") is not True:
            blockers.append("PHASE9_2_FILLED_METADATA_VALIDATION_TEMPLATE_MUST_BE_REVIEW_ONLY_NO_ORDER_SUBMIT")
        unsafe = _unsafe_true_fields(template)
        if unsafe:
            blockers.append("PHASE9_2_FILLED_METADATA_VALIDATION_TEMPLATE_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    return not blockers, blockers


def build_operator_filled_result_skeleton(template: Mapping[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    base_result = dict(template.get("operator_supplied_result_placeholder", {})) if isinstance(template.get("operator_supplied_result_placeholder"), Mapping) else {}
    payload = {
        "artifact_type": "phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_REVIEW_ONLY",
        "phase9_2_public_metadata_probe_result_filled_validation_version": PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_VERSION,
        "source_result_template_sha256": _hash(template),
        "review_only": True,
        "no_order_submit": True,
        "filled_result_validation_only": True,
        "result_intake_only": True,
        "operator_supplied_result": base_result,
        "operator_attestation": {
            "public_metadata_endpoints_only": True,
            "no_order_endpoint_called": True,
            "no_order_status_endpoint_called": True,
            "no_cancel_endpoint_called": True,
            "no_private_account_endpoint_called": True,
            "no_api_key_or_secret_used": True,
            "no_signature_created": True,
        },
        "operator_filled_public_metadata_probe_result_validated": False,
        "public_metadata_network_probe_result_validated": False,
        "real_testnet_metadata_conditions_ready_for_submit_review_only": False,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_public_metadata_probe_result_filled_skeleton_sha256"] = sha256_json(payload)
    return payload


def validate_operator_filled_probe_result(payload: Mapping[str, Any], *, source_template: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    base_validation = validate_public_metadata_probe_result_payload(data)
    errors = list(base_validation.get("block_reasons", []))
    att = data.get("operator_attestation")
    att = dict(att) if isinstance(att, Mapping) else {}
    if data.get("filled_result_validation_only") is not True:
        errors.append("PHASE9_2_FILLED_METADATA_RESULT_REQUIRES_FILLED_VALIDATION_ONLY_TRUE")
    for field in [
        "public_metadata_endpoints_only",
        "no_order_endpoint_called",
        "no_order_status_endpoint_called",
        "no_cancel_endpoint_called",
        "no_private_account_endpoint_called",
        "no_api_key_or_secret_used",
        "no_signature_created",
    ]:
        if att.get(field) is not True:
            errors.append("PHASE9_2_FILLED_METADATA_RESULT_OPERATOR_ATTESTATION_MISSING_OR_FALSE:" + field)
    result = data.get("operator_supplied_result")
    result = dict(result) if isinstance(result, Mapping) else {}
    synthetic_markers = []
    for key in ["sample_only", "synthetic", "mock_data", "fixture_only", "dummy_data"]:
        if data.get(key) is True or result.get(key) is True:
            synthetic_markers.append(key)
    source_command = str(result.get("source_probe_command_id", ""))
    if "SAMPLE" in source_command.upper() or "PLACEHOLDER" in source_command.upper() or "DUMMY" in source_command.upper():
        synthetic_markers.append("source_probe_command_id")
    if synthetic_markers:
        errors.append("PHASE9_2_FILLED_METADATA_RESULT_SAMPLE_SYNTHETIC_OR_PLACEHOLDER_DATA_BLOCKED:" + ",".join(sorted(set(synthetic_markers))))
    for endpoint in ["exchange_time_result", "exchange_info_result", "symbol_info_result"]:
        item = result.get(endpoint)
        if isinstance(item, Mapping):
            redacted_hash = str(item.get("redacted_response_sha256", ""))
            if len(redacted_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in redacted_hash):
                errors.append("PHASE9_2_FILLED_METADATA_RESULT_REQUIRES_64_HEX_REDACTED_RESPONSE_HASH:" + endpoint)
    if source_template:
        src_hash = data.get("source_result_template_sha256")
        if src_hash and src_hash != _hash(source_template):
            errors.append("PHASE9_2_FILLED_METADATA_RESULT_TEMPLATE_HASH_MISMATCH")
    unsafe = sorted(set(base_validation.get("unsafe_true_fields", []) + _unsafe_true_fields(data)))
    if unsafe:
        errors.append("PHASE9_2_FILLED_METADATA_RESULT_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    output = {
        "artifact_type": "phase9_2_public_metadata_probe_result_filled_validation_report",
        "phase9_2_public_metadata_probe_result_filled_validation_version": PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_VERSION,
        "review_only": True,
        "no_order_submit": True,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "operator_filled_public_metadata_probe_result_payload_valid": not errors,
        "operator_filled_public_metadata_probe_result_validated": bool(not errors),
        "public_metadata_network_probe_result_validated": bool(not errors),
        "real_testnet_metadata_conditions_ready_for_submit_review_only": bool(not errors),
        "real_testnet_submit_may_begin": False,
        "required_result_fields": REQUIRED_RESULT_FIELDS,
        "unsafe_true_fields": unsafe,
        "secret_like_values_detected": bool(base_validation.get("secret_like_values_detected")),
        "block_reasons": errors,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_public_metadata_probe_result_filled_validation_report_sha256"] = sha256_json(output)
    return output


def build_negative_fixture_results(template: Mapping[str, Any]) -> dict[str, Any]:
    base = build_operator_filled_result_skeleton(template, created_at_utc="2026-01-01T00:00:00Z")
    fixtures: dict[str, dict[str, Any]] = {}
    result = dict(base["operator_supplied_result"])
    fixtures["order_endpoint_called_true"] = {**base, "operator_supplied_result": {**result, "order_endpoint_called": True}}
    fixtures["private_endpoint_called_true"] = {**base, "operator_supplied_result": {**result, "private_account_endpoint_called": True}}
    fixtures["signature_required_true"] = {**base, "operator_supplied_result": {**result, "requires_signature": True}}
    fixtures["missing_attestation"] = {**base, "operator_attestation": {}}
    bad_hash_result = {**result}
    if isinstance(bad_hash_result.get("exchange_time_result"), Mapping):
        bad_hash_result["exchange_time_result"] = {**bad_hash_result["exchange_time_result"], "redacted_response_sha256": "PLACEHOLDER"}
    fixtures["bad_redacted_hash"] = {**base, "operator_supplied_result": bad_hash_result}
    fixtures["unsafe_submit_flag_true"] = {**base, "real_testnet_submit_may_begin": True}
    results: dict[str, Any] = {}
    for name, payload in fixtures.items():
        validation = validate_operator_filled_probe_result(payload, source_template=template)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    output = {
        "artifact_type": "phase9_2_public_metadata_probe_result_filled_validation_negative_fixture_results",
        "review_only": True,
        "no_order_submit": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_public_metadata_probe_result_filled_validation_negative_fixture_results_sha256"] = sha256_json(output)
    return output


def build_phase9_2_public_metadata_probe_result_filled_validation_report(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    intake = _read_latest_json(cfg, SOURCE_INTAKE_REPORT)
    template = _read_latest_json(cfg, SOURCE_TEMPLATE)
    source_ok, source_blockers = _source_ready(intake, template)
    filled_name, filled = _find_filled_result(cfg)
    skeleton = build_operator_filled_result_skeleton(template, created_at_utc=created_at_utc) if template else {}
    if filled:
        validation = validate_operator_filled_probe_result(filled, source_template=template)
        status = STATUS_VALIDATED if not validation["blocked"] and not source_blockers else STATUS_BLOCKED
        filled_present = True
        waiting_for_filled_result = False
    else:
        validation = {
            "artifact_type": "phase9_2_public_metadata_probe_result_filled_validation_report",
            "review_only": True,
            "no_order_submit": True,
            "blocked": False,
            "fail_closed": False,
            "operator_filled_public_metadata_probe_result_payload_valid": False,
            "operator_filled_public_metadata_probe_result_validated": False,
            "public_metadata_network_probe_result_validated": False,
            "real_testnet_metadata_conditions_ready_for_submit_review_only": False,
            "real_testnet_submit_may_begin": False,
            "block_reasons": [],
            **_disabled_payload(),
            "created_at_utc": created_at_utc,
        }
        status = STATUS_AWAITING if source_ok else STATUS_BLOCKED
        filled_present = False
        waiting_for_filled_result = True
    blockers = list(source_blockers) + list(validation.get("block_reasons", []))
    report_id = stable_id("phase9_2_public_metadata_probe_result_filled_validation", {
        "intake_hash": _hash(intake),
        "template_hash": _hash(template),
        "filled_hash": _hash(filled),
        "version": PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_VERSION,
    }, 24)
    validated = bool(filled_present and not blockers and validation.get("operator_filled_public_metadata_probe_result_validated"))
    report = {
        "artifact_type": "phase9_2_public_metadata_probe_result_filled_validation_orchestration_report",
        "phase9_2_public_metadata_probe_result_filled_validation_id": report_id,
        "phase9_2_public_metadata_probe_result_filled_validation_version": PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_VERSION,
        "status": STATUS_BLOCKED if blockers else status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "no_order_submit": True,
        "source_intake_present": bool(intake),
        "source_template_present": bool(template),
        "source_template_sha256": _hash(template),
        "operator_filled_result_filename": filled_name,
        "operator_filled_result_present": filled_present,
        "waiting_for_operator_filled_result": waiting_for_filled_result,
        "operator_filled_public_metadata_probe_result_validated": validated,
        "public_metadata_network_probe_result_validated": validated,
        "real_testnet_metadata_conditions_ready_for_submit_review_only": validated,
        "real_testnet_submit_may_begin": False,
        "next_action_if_validated": "prepare_explicit_real_testnet_one_order_submit_approval_but_keep_submit_disabled_until_separate_command",
        "block_reasons": blockers,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_public_metadata_probe_result_filled_validation_orchestration_report_sha256"] = sha256_json(report)
    return report, skeleton, validation


def persist_phase9_2_public_metadata_probe_result_filled_validation(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, skeleton, validation = build_phase9_2_public_metadata_probe_result_filled_validation_report(cfg=cfg)
    template = _read_latest_json(cfg, SOURCE_TEMPLATE)
    negative = build_negative_fixture_results(template) if template else {"artifact_type": "phase9_2_public_metadata_probe_result_filled_validation_negative_fixture_results", "review_only": True, "no_order_submit": True, "all_negative_fixtures_blocked_fail_closed": False, "fixture_results": {}, **_disabled_payload(), "created_at_utc": utc_now_canonical()}
    files: dict[str, Mapping[str, Any]] = {
        "phase9_2_public_metadata_probe_result_filled_validation_report.json": report,
        "phase9_2_public_metadata_probe_result_filled_validation_payload_validation_report.json": validation,
        "phase9_2_public_metadata_probe_result_filled_validation_negative_fixture_results.json": negative,
    }
    if skeleton:
        files["phase9_2_public_metadata_network_dry_probe_RESULT_FILLED_TEMPLATE_NO_ORDER_SUBMIT_REVIEW_ONLY.json"] = skeleton
    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)
    handoff = "\n".join([
        "# Phase 9.2 Public Metadata Probe Result Filled Validation / No Order Submit",
        "",
        "This packet validates an operator-filled public metadata probe result file only.",
        "It never submits orders, calls private endpoints, creates signatures, or reads API secrets.",
        "A valid metadata result may support a later manual real-testnet one-order approval review, but does not grant submit authority.",
    ])
    (latest / "PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")
    record = append_registry_record(
        registry_path(cfg, PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_public_metadata_probe_result_filled_validation_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_order_submit": True,
            "sha256": report["phase9_2_public_metadata_probe_result_filled_validation_orchestration_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_REGISTRY_NAME,
        id_field="phase9_2_public_metadata_probe_result_filled_validation_registry_id",
        hash_field="phase9_2_public_metadata_probe_result_filled_validation_registry_record_sha256",
        id_prefix="phase9_2_public_metadata_probe_result_filled_validation_registry",
    )
    atomic_write_json(latest / "phase9_2_public_metadata_probe_result_filled_validation_registry_record.json", record)
    return report
