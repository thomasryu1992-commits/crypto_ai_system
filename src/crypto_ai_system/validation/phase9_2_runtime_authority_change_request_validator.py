from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import (
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED,
    _artifact_hash,
    _find_secret_like_values,
    _flag_false_payload,
    _safe_bool,
    _unsafe_fields,
    persist_phase9_2_runtime_authority_change_request_report,
)

PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_VERSION = "phase9_2_runtime_authority_change_request_validator_v1"
PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_REGISTRY_NAME = "phase9_2_runtime_authority_change_request_validator_registry"
STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED = (
    "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED_REVIEW_ONLY"
)
STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_BLOCKED_REVIEW_ONLY = (
    "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_BLOCKED_REVIEW_ONLY"
)

REQUIRED_SOURCE_FILES = {
    "phase9_2_runtime_authority_change_request_report": "phase9_2_runtime_authority_change_request_report.json",
    "phase9_2_runtime_authority_change_request_template": "runtime_authority_change_request_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json",
    "phase9_2_runtime_authority_change_request_validation": "phase9_2_runtime_authority_change_request_validation_report.json",
    "phase9_2_runtime_authority_bridge_report": "phase9_2_runtime_authority_bridge_report.json",
    "phase9_2_real_submit_gate_report": "phase9_2_real_submit_enablement_gate_report.json",
    "phase8_3_hot_path_risk_gate_report": "phase8_3_hot_path_preorder_risk_gate_report.json",
}

RUNTIME_AUTHORITY_REQUEST_REQUIRED_FIELDS = [
    "operator_runtime_authority_request",
    "operator_signature",
    "operator_change_ticket_or_record_id",
    "metadata_only_testnet_key_fingerprint_sha256",
    "secret_manager_runtime_binding_requested",
    "secret_manager_runtime_binding_performed",
    "fresh_preorder_risk_gate_refresh_required_immediately_before_phase9_2",
    "fresh_preorder_risk_gate_refresh_performed_for_actual_endpoint_time",
    "signed_testnet_executor_enablement_policy_change_requested",
    "signed_testnet_executor_enabled",
    "order_endpoint_policy_change_requested",
    "endpoint_policy_changed",
    "single_order_runtime_scope",
    "max_order_count",
    "small_max_notional_usd",
    "daily_loss_cap_usd",
    "kill_switch_confirmed_for_runtime_authority_review",
    "mainnet_key_scope_allowed",
]

REMAINING_VALIDATOR_BLOCKERS = [
    "PHASE9_2_VALIDATOR_DOES_NOT_GRANT_RUNTIME_AUTHORITY",
    "PHASE9_2_VALIDATOR_REQUIRES_SEPARATE_EXECUTOR_POLICY_APPLICATION",
    "PHASE9_2_VALIDATOR_REQUIRES_SEPARATE_ENDPOINT_POLICY_APPLICATION",
    "PHASE9_2_VALIDATOR_REQUIRES_FRESH_RISK_REFRESH_AT_REAL_ENDPOINT_TIME",
    "PHASE9_2_VALIDATOR_REQUIRES_SECRET_MANAGER_RUNTIME_BINDING_OUTSIDE_REVIEW_ARTIFACTS",
]

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_TOKENS = ("placeholder", "must_fill", "required", "todo", "fixture_missing", "op_", "not_fixture")


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
        "status": data.get("status") or data.get("artifact_type") or data.get("gate_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_2_runtime_authority_change_request_report":
        return (
            data.get("status") == STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED
            and data.get("phase9_2_runtime_authority_change_request_recorded") is True
            and data.get("runtime_authority_change_request_approved") is False
            and data.get("runtime_authority_granted") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_2_runtime_authority_change_request_template":
        return (
            data.get("artifact_type") == "phase9_2_runtime_authority_change_request_template_review_only"
            and data.get("review_only") is True
            and data.get("still_disabled") is True
            and data.get("runtime_authority_change_request_approved") is False
            and data.get("runtime_authority_granted") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_2_runtime_authority_change_request_validation":
        return data.get("phase9_2_runtime_authority_change_request_valid") is True
    if name == "phase9_2_runtime_authority_bridge_report":
        return data.get("runtime_authority_granted") is False and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_real_submit_gate_report":
        return data.get("phase9_2_real_submit_preconditions_ready_for_manual_runtime_review") is True and data.get("phase9_2_real_submit_authorized") is False
    if name == "phase8_3_hot_path_risk_gate_report":
        return data.get("phase8_3_hot_path_risk_gate_ready") is True and data.get("phase8_4_final_guard_may_begin") is True
    return True


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    text = value.strip().lower()
    return any(token in text for token in PLACEHOLDER_TOKENS)


def _runtime_unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in FALSE_FLAGS if _safe_bool(data.get(field))]
    extra_false = [
        "runtime_authority_granted",
        "runtime_authority_change_request_approved",
        "runtime_authority_validator_approved",
        "secret_manager_runtime_binding_performed",
        "runtime_key_value_loaded",
        "runtime_api_secret_loaded",
        "runtime_private_key_loaded",
        "signed_testnet_executor_enabled",
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "endpoint_policy_changed",
        "phase9_2_real_submit_authorized",
        "phase9_2_order_submission_authorized",
        "phase9_3_status_polling_may_begin",
        "real_order_id_created",
        "order_endpoint_called",
        "order_status_endpoint_called",
        "cancel_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "actual_order_submission_performed",
    ]
    fields.extend([field for field in extra_false if _safe_bool(data.get(field))])
    fields.extend(unsafe_truthy_fields(data))
    return sorted(dict.fromkeys(fields))


def build_operator_filled_change_request_fixture(template: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(template or {})
    fixture = {
        "artifact_type": "phase9_2_operator_filled_runtime_authority_change_request_fixture_review_only",
        "review_only": True,
        "still_disabled": True,
        "source_change_request_id": source.get("change_request_id") or "missing_change_request_id",
        "source_change_request_hash": source.get("phase9_2_runtime_authority_change_request_template_sha256") or sha256_json(source),
        "operator_runtime_authority_request": "request_single_signed_testnet_order_runtime_authority_review_only",
        "operator_signature": "operator_signature_fixture_sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "operator_change_ticket_or_record_id": "runtime-authority-change-ticket-fixture-0001",
        "metadata_only_testnet_key_fingerprint_sha256": "b" * 64,
        "secret_manager_runtime_binding_requested": True,
        "secret_manager_runtime_binding_performed": False,
        "fresh_preorder_risk_gate_refresh_required_immediately_before_phase9_2": True,
        "fresh_preorder_risk_gate_refresh_performed_for_actual_endpoint_time": False,
        "signed_testnet_executor_enablement_policy_change_requested": True,
        "signed_testnet_executor_enabled": False,
        "order_endpoint_policy_change_requested": True,
        "endpoint_policy_changed": False,
        "single_order_runtime_scope": True,
        "max_order_count": 1,
        "small_max_notional_usd": 10.0,
        "daily_loss_cap_usd": 15.0,
        "kill_switch_confirmed_for_runtime_authority_review": True,
        "mainnet_key_scope_allowed": False,
        "runtime_authority_validator_approved": False,
        "runtime_authority_granted": False,
        "runtime_authority_change_request_approved": False,
        "secret_manager_runtime_binding_performed": False,
        "runtime_key_value_loaded": False,
        "runtime_api_secret_loaded": False,
        "runtime_private_key_loaded": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "real_order_id_created": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        **_flag_false_payload(),
    }
    fixture["phase9_2_operator_filled_change_request_fixture_sha256"] = sha256_json(fixture)
    return fixture


def validate_operator_filled_runtime_authority_change_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    blockers: list[str] = []
    unsafe = _runtime_unsafe_fields(data)
    secret_like_values = _find_secret_like_values(data)
    if data.get("artifact_type") != "phase9_2_operator_filled_runtime_authority_change_request_fixture_review_only":
        blockers.append("PHASE9_2_VALIDATOR_REQUEST_TYPE_INVALID")
    if data.get("review_only") is not True:
        blockers.append("PHASE9_2_VALIDATOR_REQUEST_NOT_REVIEW_ONLY")
    if data.get("still_disabled") is not True:
        blockers.append("PHASE9_2_VALIDATOR_REQUEST_NOT_STILL_DISABLED")
    for field in RUNTIME_AUTHORITY_REQUEST_REQUIRED_FIELDS:
        if field not in data or data.get(field) in (None, ""):
            blockers.append(f"PHASE9_2_VALIDATOR_REQUIRED_FIELD_MISSING:{field}")
    for field in ("operator_runtime_authority_request", "operator_signature", "operator_change_ticket_or_record_id"):
        if _is_placeholder(data.get(field)):
            blockers.append(f"PHASE9_2_VALIDATOR_PLACEHOLDER_VALUE:{field}")
    fingerprint = str(data.get("metadata_only_testnet_key_fingerprint_sha256") or "")
    if not HEX64_RE.match(fingerprint) or len(set(fingerprint)) < 1:
        blockers.append("PHASE9_2_VALIDATOR_TESTNET_KEY_FINGERPRINT_INVALID")
    if _is_placeholder(fingerprint):
        blockers.append("PHASE9_2_VALIDATOR_TESTNET_KEY_FINGERPRINT_PLACEHOLDER")
    if data.get("secret_manager_runtime_binding_requested") is not True:
        blockers.append("PHASE9_2_VALIDATOR_SECRET_MANAGER_BINDING_NOT_REQUESTED")
    if data.get("secret_manager_runtime_binding_performed") is not False:
        blockers.append("PHASE9_2_VALIDATOR_SECRET_MANAGER_BINDING_PERFORMED_UNEXPECTED")
    if data.get("fresh_preorder_risk_gate_refresh_required_immediately_before_phase9_2") is not True:
        blockers.append("PHASE9_2_VALIDATOR_FRESH_RISK_REFRESH_NOT_REQUIRED")
    if data.get("fresh_preorder_risk_gate_refresh_performed_for_actual_endpoint_time") is not False:
        blockers.append("PHASE9_2_VALIDATOR_FRESH_RISK_REFRESH_ALREADY_PERFORMED_UNEXPECTED")
    if data.get("signed_testnet_executor_enablement_policy_change_requested") is not True:
        blockers.append("PHASE9_2_VALIDATOR_EXECUTOR_POLICY_CHANGE_NOT_REQUESTED")
    if data.get("signed_testnet_executor_enabled") is not False:
        blockers.append("PHASE9_2_VALIDATOR_EXECUTOR_ENABLED_UNEXPECTED")
    if data.get("order_endpoint_policy_change_requested") is not True:
        blockers.append("PHASE9_2_VALIDATOR_ENDPOINT_POLICY_CHANGE_NOT_REQUESTED")
    if data.get("endpoint_policy_changed") is not False:
        blockers.append("PHASE9_2_VALIDATOR_ENDPOINT_POLICY_CHANGED_UNEXPECTED")
    if data.get("single_order_runtime_scope") is not True:
        blockers.append("PHASE9_2_VALIDATOR_SINGLE_ORDER_SCOPE_MISSING")
    try:
        max_count = int(data.get("max_order_count"))
    except (TypeError, ValueError):
        max_count = 0
        blockers.append("PHASE9_2_VALIDATOR_MAX_ORDER_COUNT_INVALID")
    if max_count != 1:
        blockers.append("PHASE9_2_VALIDATOR_MAX_ORDER_COUNT_NOT_ONE")
    try:
        max_notional = float(data.get("small_max_notional_usd"))
    except (TypeError, ValueError):
        max_notional = 0.0
        blockers.append("PHASE9_2_VALIDATOR_MAX_NOTIONAL_INVALID")
    if max_notional <= 0 or max_notional > 10.0:
        blockers.append("PHASE9_2_VALIDATOR_MAX_NOTIONAL_EXCEEDS_SMALL_CAP")
    try:
        daily_loss_cap = float(data.get("daily_loss_cap_usd"))
    except (TypeError, ValueError):
        daily_loss_cap = 0.0
        blockers.append("PHASE9_2_VALIDATOR_DAILY_LOSS_CAP_INVALID")
    if daily_loss_cap <= 0 or daily_loss_cap > 15.0:
        blockers.append("PHASE9_2_VALIDATOR_DAILY_LOSS_CAP_EXCEEDS_LIMIT")
    if data.get("kill_switch_confirmed_for_runtime_authority_review") is not True:
        blockers.append("PHASE9_2_VALIDATOR_KILL_SWITCH_NOT_CONFIRMED")
    if data.get("mainnet_key_scope_allowed") is not False:
        blockers.append("PHASE9_2_VALIDATOR_MAINNET_KEY_SCOPE_ALLOWED_UNEXPECTED")
    if unsafe:
        blockers.append("PHASE9_2_VALIDATOR_UNSAFE_FLAGS:" + ",".join(unsafe))
    if secret_like_values:
        blockers.append("PHASE9_2_VALIDATOR_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like_values))
    field_level_valid = not blockers
    return {
        "artifact_type": "phase9_2_runtime_authority_change_request_operator_values_validation_report",
        "phase9_2_operator_filled_request_field_level_valid": field_level_valid,
        "blocked": not field_level_valid,
        "fail_closed": not field_level_valid,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like_values,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "runtime_authority_validator_approved": False,
        "runtime_authority_granted": False,
        "phase9_2_order_submission_authorized": False,
        **_flag_false_payload(),
    }


def _build_negative_fixture_results(valid_fixture: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "placeholder_operator_signature": {"operator_signature": "OPERATOR_SIGNATURE_REQUIRED"},
        "missing_operator_change_ticket": {"operator_change_ticket_or_record_id": ""},
        "placeholder_key_fingerprint": {"metadata_only_testnet_key_fingerprint_sha256": "KEY_FINGERPRINT_PLACEHOLDER"},
        "raw_secret_value_present": {"api_secret": "raw-secret-value-should-block"},
        "mainnet_key_scope_allowed": {"mainnet_key_scope_allowed": True},
        "max_order_count_gt_one": {"max_order_count": 2},
        "max_notional_too_large": {"small_max_notional_usd": 1000.0},
        "daily_loss_cap_too_large": {"daily_loss_cap_usd": 500.0},
        "kill_switch_not_confirmed": {"kill_switch_confirmed_for_runtime_authority_review": False},
        "secret_binding_already_performed": {"secret_manager_runtime_binding_performed": True},
        "executor_enabled_true": {"signed_testnet_executor_enabled": True},
        "endpoint_policy_changed_true": {"endpoint_policy_changed": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "signature_created_true": {"signature_created": True},
        "http_request_sent_true": {"http_request_sent": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(valid_fixture)
        payload.update(patch)
        validation = validate_operator_filled_runtime_authority_change_request(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_runtime_authority_change_request_validator_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def build_phase9_2_runtime_authority_change_request_validator_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_change_request_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_change_request_first:
        persist_phase9_2_runtime_authority_change_request_report(cfg=cfg, run_runtime_authority_bridge_first=True)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    evidence_ready = not missing and not not_ready and not unsafe

    template = sources.get("phase9_2_runtime_authority_change_request_template", {})
    operator_fixture = build_operator_filled_change_request_fixture(template)
    operator_fixture_validation = validate_operator_filled_runtime_authority_change_request(operator_fixture)
    negative_fixture_results = _build_negative_fixture_results(operator_fixture)

    source_change_request_id = str(template.get("change_request_id") or "missing_change_request_id")
    source_change_request_hash = str(template.get("phase9_2_runtime_authority_change_request_template_sha256") or _artifact_hash(template) or "missing")
    validator_id = stable_id(
        "phase9_2_runtime_authority_change_request_validator",
        {"source_change_request_id": source_change_request_id, "source_change_request_hash": source_change_request_hash, "created_at_utc": created},
        24,
    )
    recorded = evidence_ready and operator_fixture_validation["phase9_2_operator_filled_request_field_level_valid"] is True and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    status = STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED if recorded else STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_BLOCKED_REVIEW_ONLY
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_CHANGE_REQUEST_VALIDATOR_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_CHANGE_REQUEST_VALIDATOR_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_CHANGE_REQUEST_VALIDATOR_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers.extend(REMAINING_VALIDATOR_BLOCKERS)
    report = {
        "phase9_2_runtime_authority_change_request_validator_id": validator_id,
        "phase9_2_runtime_authority_change_request_validator_version": PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_runtime_authority_change_request_validator_recorded": recorded,
        "operator_filled_request_field_level_valid": operator_fixture_validation["phase9_2_operator_filled_request_field_level_valid"],
        "operator_filled_request_fixture_is_runtime_authority": False,
        "validator_grants_runtime_authority": False,
        "runtime_authority_granted": False,
        "runtime_authority_validator_approved": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "source_phase9_2_runtime_authority_change_request_id": source_change_request_id,
        "source_phase9_2_runtime_authority_change_request_hash": source_change_request_hash,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "operator_fixture_validation_report": operator_fixture_validation,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers + operator_fixture_validation.get("block_reasons", []))),
        "recommended_next_action": "keep_change_request_validator_still_disabled_and_require_real_manual_authority_application_boundary_before_any_endpoint_call",
        **_flag_false_payload(),
        "secret_manager_runtime_binding_performed": False,
        "signed_testnet_executor_enabled": False,
        "endpoint_policy_changed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_2_runtime_authority_change_request_validator_report_sha256"] = sha256_json(report)
    return report, operator_fixture, operator_fixture_validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Runtime Authority Change Request Validator - Still Disabled",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This validator checks operator-filled runtime authority change request fields, placeholder use, metadata-only key fingerprint format, one-order caps, secret exposure, and still-disabled execution flags. It does not grant runtime authority or submit orders.",
            "",
            "## Result",
            "",
            f"- Operator-filled request field-level valid: `{report.get('operator_filled_request_field_level_valid')}`",
            f"- Validator grants runtime authority: `{report.get('validator_grants_runtime_authority')}`",
            f"- Runtime authority granted: `{report.get('runtime_authority_granted')}`",
            f"- Phase 9.2 order submission authorized: `{report.get('phase9_2_order_submission_authorized')}`",
            "",
            "## Still Disabled",
            "",
            "- `runtime_authority_granted=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `secret_manager_runtime_binding_performed=false`",
            "- `endpoint_policy_changed=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "- `actual_order_submission_performed=false`",
            "",
        ]
    )


def persist_phase9_2_runtime_authority_change_request_validator_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_change_request_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_runtime_authority_change_request_validator")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, operator_fixture, operator_fixture_validation, negative_fixture_results = build_phase9_2_runtime_authority_change_request_validator_report(
        cfg=cfg,
        run_change_request_first=run_change_request_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_runtime_authority_change_request_validator_report.json", report)
        atomic_write_json(base / "runtime_authority_change_request_OPERATOR_FILLED_FIXTURE_STILL_DISABLED_REVIEW_ONLY.json", operator_fixture)
        atomic_write_json(base / "phase9_2_runtime_authority_change_request_operator_values_validation_report.json", operator_fixture_validation)
        atomic_write_json(base / "phase9_2_runtime_authority_change_request_validator_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_REGISTRY_NAME),
        {
            "phase9_2_runtime_authority_change_request_validator_id": report.get("phase9_2_runtime_authority_change_request_validator_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "validator_grants_runtime_authority": False,
            "runtime_authority_granted": False,
            "phase9_2_order_submission_authorized": False,
            "secret_manager_runtime_binding_performed": False,
            "signed_testnet_executor_enabled": False,
            "endpoint_policy_changed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_REGISTRY_NAME,
        id_field="phase9_2_runtime_authority_change_request_validator_registry_record_id",
        hash_field="phase9_2_runtime_authority_change_request_validator_registry_record_sha256",
        id_prefix="phase9_2_runtime_authority_change_request_validator_registry_record",
    )
    atomic_write_json(latest / "phase9_2_runtime_authority_change_request_validator_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_runtime_authority_change_request_validator_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_VERSION",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_BLOCKED_REVIEW_ONLY",
    "RUNTIME_AUTHORITY_REQUEST_REQUIRED_FIELDS",
    "REMAINING_VALIDATOR_BLOCKERS",
    "build_operator_filled_change_request_fixture",
    "validate_operator_filled_runtime_authority_change_request",
    "build_phase9_2_runtime_authority_change_request_validator_report",
    "persist_phase9_2_runtime_authority_change_request_validator_report",
]
