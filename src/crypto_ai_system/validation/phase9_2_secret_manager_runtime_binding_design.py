from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_endpoint_time_risk_refresh_design import (
    STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED,
    persist_phase9_2_endpoint_time_risk_refresh_report,
)
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import (
    _artifact_hash,
    _find_secret_like_values,
    _flag_false_payload,
    _safe_bool,
    _unsafe_fields,
)

PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_VERSION = "phase9_2_secret_manager_runtime_binding_design_v1"
PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_REGISTRY_NAME = "phase9_2_secret_manager_runtime_binding_registry"
STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_RECORDED_STILL_DISABLED = (
    "PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_RECORDED_STILL_DISABLED_REVIEW_ONLY"
)
STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_BLOCKED_REVIEW_ONLY = (
    "PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_BLOCKED_REVIEW_ONLY"
)

REQUIRED_SOURCE_FILES = {
    "phase9_2_endpoint_time_risk_refresh_report": "phase9_2_endpoint_time_risk_refresh_report.json",
    "phase9_2_runtime_authority_application_boundary_report": "phase9_2_runtime_authority_application_boundary_report.json",
    "phase9_2_runtime_authority_change_request_validator_report": "phase9_2_runtime_authority_change_request_validator_report.json",
    "phase8_1_secret_manager_key_handling_design_report": "phase8_1_secret_manager_key_handling_design_report.json",
    "phase9_2_real_submit_enablement_gate_report": "phase9_2_real_submit_enablement_gate_report.json",
}

BINDING_REQUIRED_FIELDS = [
    "secret_manager_runtime_binding_design_id",
    "source_endpoint_time_risk_refresh_id",
    "source_endpoint_time_risk_refresh_hash",
    "source_secret_manager_design_hash",
    "runtime_binding_scope",
    "metadata_only_key_reference_required",
    "metadata_only_testnet_key_fingerprint_sha256",
    "secret_value_read_allowed",
    "api_key_value_read_allowed",
    "api_secret_value_read_allowed",
    "private_key_read_allowed",
    "passphrase_read_allowed",
    "secret_file_read_allowed",
    "secret_file_created",
    "runtime_secret_binding_required_before_real_submit",
    "secret_manager_runtime_binding_performed",
    "signature_creation_allowed",
    "signed_request_creation_allowed",
    "order_endpoint_call_allowed",
    "runtime_authority_granted",
    "phase9_2_order_submission_authorized",
]

REMAINING_SECRET_BINDING_BLOCKERS = [
    "PHASE9_2_SECRET_BINDING_REQUIRES_REAL_SECRET_MANAGER_ADAPTER_OUTSIDE_REVIEW_ARTIFACTS",
    "PHASE9_2_SECRET_BINDING_REQUIRES_REAL_OPERATOR_APPROVAL_RECORD_NOT_FIXTURE",
    "PHASE9_2_SECRET_BINDING_REQUIRES_ENDPOINT_TIME_RISK_REFRESH_EXECUTION_AT_SUBMIT_TIME",
    "PHASE9_2_SECRET_BINDING_REQUIRES_EXECUTOR_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_SECRET_BINDING_REQUIRES_ENDPOINT_POLICY_APPLICATION_NOT_PRESENT",
    "PHASE9_2_SECRET_BINDING_DOES_NOT_CREATE_SIGNATURE_OR_HTTP_REQUEST",
]


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


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_2_endpoint_time_risk_refresh_report":
        return (
            data.get("status") == STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED
            and data.get("phase9_2_endpoint_time_risk_refresh_recorded") is True
            and data.get("endpoint_time_risk_refresh_design_ready") is True
            and data.get("endpoint_time_risk_refresh_performed") is False
            and data.get("secret_manager_runtime_binding_performed") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_2_runtime_authority_application_boundary_report":
        return data.get("runtime_authority_application_boundary_template_valid") is True and data.get("runtime_authority_application_performed") is False
    if name == "phase9_2_runtime_authority_change_request_validator_report":
        return data.get("operator_filled_request_field_level_valid") is True and data.get("runtime_authority_granted") is False
    if name == "phase8_1_secret_manager_key_handling_design_report":
        return data.get("phase8_1_secret_key_design_ready") is True and data.get("metadata_only_key_handling") is True and data.get("secret_value_accessed") is False
    if name == "phase9_2_real_submit_enablement_gate_report":
        return data.get("phase9_2_real_submit_preconditions_ready_for_manual_runtime_review") is True and data.get("phase9_2_real_submit_authorized") is False
    return True


def _runtime_unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in FALSE_FLAGS if _safe_bool(data.get(field))]
    extra_false = [
        "secret_manager_runtime_binding_performed",
        "runtime_key_value_loaded",
        "runtime_api_secret_loaded",
        "runtime_private_key_loaded",
        "runtime_passphrase_loaded",
        "secret_file_read",
        "secret_file_created",
        "secret_value_read_allowed",
        "api_key_value_read_allowed",
        "api_secret_value_read_allowed",
        "private_key_read_allowed",
        "passphrase_read_allowed",
        "secret_file_read_allowed",
        "signature_creation_allowed",
        "signed_request_creation_allowed",
        "order_endpoint_call_allowed",
        "signature_created",
        "signed_request_created",
        "http_request_sent",
        "order_endpoint_called",
        "runtime_authority_granted",
        "phase9_2_order_submission_authorized",
        "signed_order_executor_enabled",
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "actual_order_submission_performed",
    ]
    fields.extend([field for field in extra_false if _safe_bool(data.get(field))])
    fields.extend(unsafe_truthy_fields(data))
    return sorted(dict.fromkeys(fields))


def build_secret_manager_runtime_binding_template(
    endpoint_time_risk_refresh_report: Mapping[str, Any], secret_design_report: Mapping[str, Any]
) -> dict[str, Any]:
    endpoint = dict(endpoint_time_risk_refresh_report or {})
    secret_design = dict(secret_design_report or {})
    source_endpoint_id = str(endpoint.get("phase9_2_endpoint_time_risk_refresh_id") or "missing_endpoint_time_risk_refresh_id")
    source_endpoint_hash = str(endpoint.get("phase9_2_endpoint_time_risk_refresh_report_sha256") or sha256_json(endpoint))
    source_secret_design_hash = str(secret_design.get("phase8_1_secret_manager_key_handling_design_report_sha256") or sha256_json(secret_design))
    binding_id = stable_id(
        "phase9_2_secret_manager_runtime_binding",
        {
            "source_endpoint_time_risk_refresh_id": source_endpoint_id,
            "source_endpoint_time_risk_refresh_hash": source_endpoint_hash,
            "source_secret_manager_design_hash": source_secret_design_hash,
        },
        24,
    )
    template = {
        "artifact_type": "phase9_2_secret_manager_runtime_binding_design_still_disabled_review_only",
        "secret_manager_runtime_binding_design_id": binding_id,
        "secret_manager_runtime_binding_version": PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_endpoint_time_risk_refresh_id": source_endpoint_id,
        "source_endpoint_time_risk_refresh_hash": source_endpoint_hash,
        "source_secret_manager_design_hash": source_secret_design_hash,
        "runtime_binding_scope": "single_signed_testnet_order_metadata_only_binding_design",
        "metadata_only_key_reference_required": True,
        "metadata_only_key_reference_placeholder": "secret_manager://testnet/binance_futures/order_submit_key_ref_PLACEHOLDER",
        "metadata_only_testnet_key_fingerprint_sha256": "f" * 64,
        "key_scope_required": "testnet_trade_only_no_withdrawal_no_transfer_no_admin_no_margin_mutation",
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
        "mainnet_key_scope_allowed": False,
        "leverage_or_margin_mutation_allowed": False,
        "secret_value_read_allowed": False,
        "api_key_value_read_allowed": False,
        "api_secret_value_read_allowed": False,
        "private_key_read_allowed": False,
        "passphrase_read_allowed": False,
        "secret_file_read_allowed": False,
        "secret_file_created": False,
        "runtime_secret_binding_required_before_real_submit": True,
        "secret_manager_runtime_binding_performed": False,
        "runtime_key_value_loaded": False,
        "runtime_api_secret_loaded": False,
        "runtime_private_key_loaded": False,
        "runtime_passphrase_loaded": False,
        "signature_creation_allowed": False,
        "signed_request_creation_allowed": False,
        "order_endpoint_call_allowed": False,
        "runtime_authority_granted": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        **_flag_false_payload(),
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
    }
    template["secret_manager_runtime_binding_template_sha256"] = sha256_json(template)
    return template


def validate_secret_manager_runtime_binding_template(template: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(template or {})
    blockers: list[str] = []
    missing = [field for field in BINDING_REQUIRED_FIELDS if field not in data]
    blockers.extend(f"PHASE9_2_SECRET_BINDING_MISSING_FIELD:{field}" for field in missing)
    unsafe = _runtime_unsafe_fields(data)
    secret_like_values = [
        path for path in _find_secret_like_values(data)
        if path not in {
            "secret_manager_runtime_binding_design_id",
            "secret_manager_runtime_binding_version",
            "secret_manager_runtime_binding_template_sha256",
            "source_secret_manager_design_hash",
            "metadata_only_key_reference_required",
            "metadata_only_key_reference_placeholder",
            "runtime_secret_binding_required_before_real_submit",
            "secret_manager_runtime_binding_performed",
            "secret_value_read_allowed",
            "api_secret_value_read_allowed",
            "secret_file_read_allowed",
            "secret_file_created",
        }
    ]
    if data.get("artifact_type") != "phase9_2_secret_manager_runtime_binding_design_still_disabled_review_only":
        blockers.append("PHASE9_2_SECRET_BINDING_INVALID_ARTIFACT_TYPE")
    if data.get("review_only") is not True or data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_SECRET_BINDING_NOT_REVIEW_ONLY_STILL_DISABLED")
    if not data.get("source_endpoint_time_risk_refresh_id") or not data.get("source_endpoint_time_risk_refresh_hash"):
        blockers.append("PHASE9_2_SECRET_BINDING_MISSING_ENDPOINT_TIME_RISK_SOURCE")
    if not data.get("source_secret_manager_design_hash"):
        blockers.append("PHASE9_2_SECRET_BINDING_MISSING_SECRET_MANAGER_DESIGN_HASH")
    if data.get("metadata_only_key_reference_required") is not True:
        blockers.append("PHASE9_2_SECRET_BINDING_METADATA_ONLY_REFERENCE_NOT_REQUIRED")
    fp = str(data.get("metadata_only_testnet_key_fingerprint_sha256") or "")
    if len(fp) != 64 or any(ch not in "0123456789abcdef" for ch in fp.lower()):
        blockers.append("PHASE9_2_SECRET_BINDING_INVALID_METADATA_ONLY_TESTNET_KEY_FINGERPRINT")
    if data.get("key_scope_required") != "testnet_trade_only_no_withdrawal_no_transfer_no_admin_no_margin_mutation":
        blockers.append("PHASE9_2_SECRET_BINDING_INVALID_KEY_SCOPE")
    for field in ["withdrawal_permission_allowed", "transfer_permission_allowed", "admin_permission_allowed", "mainnet_key_scope_allowed", "leverage_or_margin_mutation_allowed"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_SECRET_BINDING_UNSAFE_KEY_SCOPE:{field}")
    for field in ["secret_value_read_allowed", "api_key_value_read_allowed", "api_secret_value_read_allowed", "private_key_read_allowed", "passphrase_read_allowed", "secret_file_read_allowed", "secret_file_created"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_SECRET_BINDING_SECRET_ACCESS_ALLOWED:{field}")
    if data.get("runtime_secret_binding_required_before_real_submit") is not True:
        blockers.append("PHASE9_2_SECRET_BINDING_RUNTIME_BINDING_NOT_REQUIRED")
    if data.get("secret_manager_runtime_binding_performed") is not False:
        blockers.append("PHASE9_2_SECRET_BINDING_PERFORMED_UNEXPECTED")
    for field in ["signature_creation_allowed", "signed_request_creation_allowed", "order_endpoint_call_allowed", "runtime_authority_granted", "phase9_2_order_submission_authorized"]:
        if data.get(field) is not False:
            blockers.append(f"PHASE9_2_SECRET_BINDING_UNSAFE_RUNTIME_FLAG:{field}")
    if unsafe:
        blockers.append("PHASE9_2_SECRET_BINDING_UNSAFE_FLAGS:" + ",".join(unsafe))
    if secret_like_values:
        blockers.append("PHASE9_2_SECRET_BINDING_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like_values))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_secret_manager_runtime_binding_validation_report",
        "phase9_2_secret_manager_runtime_binding_template_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like_values,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "secret_manager_runtime_binding_performed": False,
        "runtime_authority_granted": False,
        "phase9_2_order_submission_authorized": False,
        **_flag_false_payload(),
    }


def _build_negative_fixture_results(valid_template: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "missing_endpoint_time_risk_hash": {"source_endpoint_time_risk_refresh_hash": ""},
        "placeholder_key_fingerprint": {"metadata_only_testnet_key_fingerprint_sha256": "PLACEHOLDER"},
        "mainnet_key_scope_allowed": {"mainnet_key_scope_allowed": True},
        "withdrawal_permission_allowed": {"withdrawal_permission_allowed": True},
        "transfer_permission_allowed": {"transfer_permission_allowed": True},
        "admin_permission_allowed": {"admin_permission_allowed": True},
        "secret_value_read_allowed": {"secret_value_read_allowed": True},
        "api_secret_value_read_allowed": {"api_secret_value_read_allowed": True},
        "private_key_read_allowed": {"private_key_read_allowed": True},
        "secret_file_read_allowed": {"secret_file_read_allowed": True},
        "secret_file_created": {"secret_file_created": True},
        "runtime_secret_binding_performed": {"secret_manager_runtime_binding_performed": True},
        "signature_creation_allowed": {"signature_creation_allowed": True},
        "signed_request_creation_allowed": {"signed_request_creation_allowed": True},
        "order_endpoint_call_allowed": {"order_endpoint_call_allowed": True},
        "runtime_authority_granted_true": {"runtime_authority_granted": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "raw_secret_value_present": {"api_secret": "raw-secret-value-should-block"},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "signature_created_true": {"signature_created": True},
        "http_request_sent_true": {"http_request_sent": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(valid_template)
        payload.update(patch)
        validation = validate_secret_manager_runtime_binding_template(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_secret_manager_runtime_binding_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def build_phase9_2_secret_manager_runtime_binding_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_endpoint_time_refresh_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_endpoint_time_refresh_first:
        persist_phase9_2_endpoint_time_risk_refresh_report(cfg=cfg, run_application_boundary_first=True)
    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    evidence_ready = not missing and not not_ready and not unsafe
    template = build_secret_manager_runtime_binding_template(
        sources.get("phase9_2_endpoint_time_risk_refresh_report", {}),
        sources.get("phase8_1_secret_manager_key_handling_design_report", {}),
    )
    validation = validate_secret_manager_runtime_binding_template(template)
    negative_fixture_results = _build_negative_fixture_results(template)
    binding_id = template.get("secret_manager_runtime_binding_design_id") or stable_id("phase9_2_secret_manager_runtime_binding", {"created_at_utc": created}, 24)
    recorded = evidence_ready and validation["phase9_2_secret_manager_runtime_binding_template_valid"] is True and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    status = STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_RECORDED_STILL_DISABLED if recorded else STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_BLOCKED_REVIEW_ONLY
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_SECRET_BINDING_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_SECRET_BINDING_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_SECRET_BINDING_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers.extend(REMAINING_SECRET_BINDING_BLOCKERS)
    report = {
        "phase9_2_secret_manager_runtime_binding_design_id": binding_id,
        "phase9_2_secret_manager_runtime_binding_version": PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_secret_manager_runtime_binding_recorded": recorded,
        "secret_manager_runtime_binding_design_ready": recorded,
        "secret_manager_runtime_binding_template_valid": validation["phase9_2_secret_manager_runtime_binding_template_valid"],
        "metadata_only_key_binding_design_ready": recorded,
        "secret_manager_runtime_binding_performed": False,
        "runtime_secret_value_loaded": False,
        "runtime_api_secret_loaded": False,
        "secret_value_read_allowed": False,
        "api_key_value_read_allowed": False,
        "api_secret_value_read_allowed": False,
        "private_key_read_allowed": False,
        "passphrase_read_allowed": False,
        "secret_file_read_allowed": False,
        "secret_file_created": False,
        "signature_creation_allowed": False,
        "signed_request_creation_allowed": False,
        "order_endpoint_call_allowed": False,
        "runtime_authority_granted": False,
        "endpoint_time_risk_refresh_performed": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "source_endpoint_time_risk_refresh_id": template.get("source_endpoint_time_risk_refresh_id"),
        "source_endpoint_time_risk_refresh_hash": template.get("source_endpoint_time_risk_refresh_hash"),
        "source_secret_manager_design_hash": template.get("source_secret_manager_design_hash"),
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "secret_manager_runtime_binding_validation_report": validation,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers + validation.get("block_reasons", []))),
        "recommended_next_action": "keep_secret_manager_runtime_binding_design_still_disabled_until_real_secret_manager_adapter_runtime_policy_and_endpoint_time_risk_refresh_execution_are_approved",
        **_flag_false_payload(),
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_2_secret_manager_runtime_binding_report_sha256"] = sha256_json(report)
    return report, template, validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Phase 9.2 Secret Manager Runtime Binding Design - Still Disabled",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This artifact defines how a future signed testnet submit path may bind a metadata-only key reference and fingerprint to a runtime secret-manager adapter. It does not read key values, create secret files, create signatures, send HTTP requests, call order endpoints, or authorize Phase 9.2 order submission.",
        "",
        "## Required Binding Properties",
        "",
        "- metadata-only key reference",
        "- metadata-only testnet key fingerprint",
        "- testnet trade-only scope",
        "- withdrawal / transfer / admin / mainnet permissions blocked",
        "- no raw secret values in artifacts",
        "- runtime binding required before any real submit, but not performed here",
        "",
        "## Still Disabled",
        "",
        "- `secret_manager_runtime_binding_performed=false`",
        "- `api_secret_value_read_allowed=false`",
        "- `signature_creation_allowed=false`",
        "- `order_endpoint_call_allowed=false`",
        "- `phase9_2_order_submission_authorized=false`",
        "- `actual_order_submission_performed=false`",
        "",
    ])


def persist_phase9_2_secret_manager_runtime_binding_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_endpoint_time_refresh_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_secret_manager_runtime_binding")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, validation, negative_fixture_results = build_phase9_2_secret_manager_runtime_binding_report(
        cfg=cfg,
        run_endpoint_time_refresh_first=run_endpoint_time_refresh_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_secret_manager_runtime_binding_report.json", report)
        atomic_write_json(base / "secret_manager_runtime_binding_DESIGN_STILL_DISABLED_REVIEW_ONLY.json", template)
        atomic_write_json(base / "phase9_2_secret_manager_runtime_binding_validation_report.json", validation)
        atomic_write_json(base / "phase9_2_secret_manager_runtime_binding_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_REGISTRY_NAME),
        {
            "phase9_2_secret_manager_runtime_binding_design_id": report.get("phase9_2_secret_manager_runtime_binding_design_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "secret_manager_runtime_binding_performed": False,
            "runtime_authority_granted": False,
            "phase9_2_order_submission_authorized": False,
            "signed_order_executor_enabled": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_REGISTRY_NAME,
        id_field="phase9_2_secret_manager_runtime_binding_registry_record_id",
        hash_field="phase9_2_secret_manager_runtime_binding_registry_record_sha256",
        id_prefix="phase9_2_secret_manager_runtime_binding_registry_record",
    )
    atomic_write_json(latest / "phase9_2_secret_manager_runtime_binding_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_secret_manager_runtime_binding_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_VERSION",
    "STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_RECORDED_STILL_DISABLED",
    "STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_BLOCKED_REVIEW_ONLY",
    "BINDING_REQUIRED_FIELDS",
    "REMAINING_SECRET_BINDING_BLOCKERS",
    "build_secret_manager_runtime_binding_template",
    "validate_secret_manager_runtime_binding_template",
    "build_phase9_2_secret_manager_runtime_binding_report",
    "persist_phase9_2_secret_manager_runtime_binding_report",
]
