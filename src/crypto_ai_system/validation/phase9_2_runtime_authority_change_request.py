from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_runtime_authority_bridge import (
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED,
    persist_phase9_2_runtime_authority_bridge_report,
)

PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VERSION = "phase9_2_runtime_authority_change_request_v1"
PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_REGISTRY_NAME = "phase9_2_runtime_authority_change_request_registry"
STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED = (
    "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED_REVIEW_ONLY"
)
STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_BLOCKED_REVIEW_ONLY = (
    "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_BLOCKED_REVIEW_ONLY"
)

REQUIRED_SOURCE_FILES = {
    "phase9_2_runtime_authority_bridge_report": "phase9_2_runtime_authority_bridge_report.json",
    "phase9_2_runtime_authority_bridge_artifact": "runtime_authority_bridge_STILL_DISABLED_REVIEW_ONLY.json",
    "phase9_2_runtime_authority_bridge_validation": "phase9_2_runtime_authority_bridge_validation_report.json",
    "phase9_2_real_submit_gate_report": "phase9_2_real_submit_enablement_gate_report.json",
    "phase8_3_hot_path_risk_gate_report": "phase8_3_hot_path_preorder_risk_gate_report.json",
}

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "runtime_authority_granted",
    "runtime_authority_bridge_complete",
    "runtime_authority_change_request_approved",
    "runtime_authority_change_request_complete",
    "runtime_authority_change_applied",
    "secret_manager_runtime_binding_performed",
    "runtime_key_value_loaded",
    "runtime_api_secret_loaded",
    "runtime_private_key_loaded",
    "signed_testnet_executor_enabled",
    "testnet_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "endpoint_policy_changed",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "real_order_id_created",
    "phase9_2_order_submission_authorized",
    "phase9_2_real_submit_authorized",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
]

CHANGE_REQUEST_REQUIRED_FIELDS = [
    "change_request_id",
    "source_phase9_2_runtime_authority_bridge_id",
    "source_phase9_2_runtime_authority_bridge_hash",
    "operator_runtime_authority_request_placeholder",
    "operator_signature_placeholder",
    "operator_change_ticket_placeholder",
    "secret_manager_runtime_binding_request",
    "fresh_preorder_risk_gate_refresh_request",
    "signed_testnet_executor_enablement_policy_change_request",
    "order_endpoint_policy_change_request",
    "single_order_runtime_scope",
    "max_order_count",
    "small_max_notional_usd",
    "daily_loss_cap_usd",
    "kill_switch_runtime_confirmation_required",
    "metadata_only_testnet_key_fingerprint_required",
]

CHANGE_REQUEST_REQUIRED_ACKS = [
    "ack_fixture_approval_is_not_runtime_authority",
    "ack_no_secret_values_in_request",
    "ack_runtime_secret_binding_not_performed",
    "ack_executor_still_disabled",
    "ack_endpoint_policy_not_changed",
    "ack_order_submission_still_disabled",
]

REMAINING_CHANGE_REQUEST_BLOCKERS = [
    "PHASE9_2_CHANGE_REQUEST_REQUIRES_REAL_OPERATOR_FILLED_APPROVAL_NOT_PLACEHOLDER",
    "PHASE9_2_CHANGE_REQUEST_REQUIRES_MANUAL_REVIEW_OF_SECRET_MANAGER_BINDING",
    "PHASE9_2_CHANGE_REQUEST_REQUIRES_FRESH_RISK_GATE_AT_ACTUAL_ENDPOINT_TIME",
    "PHASE9_2_CHANGE_REQUEST_REQUIRES_SEPARATE_EXECUTOR_POLICY_APPROVAL",
    "PHASE9_2_CHANGE_REQUEST_REQUIRES_SEPARATE_ENDPOINT_POLICY_APPROVAL",
]

SECRET_LIKE_FIELD_NAMES = {
    "api_key",
    "api_secret",
    "secret",
    "private_key",
    "passphrase",
    "password",
    "token",
    "key_value",
    "secret_value",
}


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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(dict.fromkeys(fields))


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_2_runtime_authority_change_request_template_sha256",
        "phase9_2_runtime_authority_change_request_report_sha256",
        "phase9_2_runtime_authority_bridge_report_sha256",
        "phase9_2_runtime_authority_bridge_artifact_sha256",
        "phase9_2_real_submit_enablement_gate_report_sha256",
        "phase8_3_hot_path_preorder_risk_gate_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


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
    if name == "phase9_2_runtime_authority_bridge_report":
        return (
            data.get("status") == STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED
            and data.get("runtime_authority_preconditions_ready_for_manual_design_review") is True
            and data.get("runtime_authority_granted") is False
            and data.get("runtime_authority_bridge_complete") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_2_runtime_authority_bridge_artifact":
        return (
            data.get("artifact_type") == "phase9_2_runtime_authority_bridge_review_only"
            and data.get("review_only") is True
            and data.get("still_disabled") is True
            and data.get("runtime_authority_granted") is False
            and data.get("runtime_authority_bridge_complete") is False
        )
    if name == "phase9_2_runtime_authority_bridge_validation":
        return data.get("phase9_2_runtime_authority_bridge_valid") is True
    if name == "phase9_2_real_submit_gate_report":
        return (
            data.get("phase9_2_real_submit_preconditions_ready_for_manual_runtime_review") is True
            and data.get("phase9_2_real_submit_authorized") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase8_3_hot_path_risk_gate_report":
        return data.get("phase8_3_hot_path_risk_gate_ready") is True and data.get("phase8_4_final_guard_may_begin") is True
    return True


def _find_secret_like_values(payload: Any, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key).lower()
            path = f"{prefix}.{key}" if prefix else str(key)
            if any(token in key_text for token in SECRET_LIKE_FIELD_NAMES):
                if isinstance(value, str) and value and "placeholder" not in value.lower() and "fingerprint" not in key_text:
                    findings.append(path)
            findings.extend(_find_secret_like_values(value, path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            findings.extend(_find_secret_like_values(value, f"{prefix}[{index}]"))
    return sorted(dict.fromkeys(findings))


def validate_phase9_2_runtime_authority_change_request(template: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(template or {})
    unsafe = _unsafe_fields(payload)
    secret_like_values = _find_secret_like_values(payload)
    blockers: list[str] = []
    if payload.get("artifact_type") != "phase9_2_runtime_authority_change_request_template_review_only":
        blockers.append("PHASE9_2_CHANGE_REQUEST_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE9_2_CHANGE_REQUEST_NOT_REVIEW_ONLY")
    if payload.get("still_disabled") is not True:
        blockers.append("PHASE9_2_CHANGE_REQUEST_NOT_STILL_DISABLED")
    for field in CHANGE_REQUEST_REQUIRED_FIELDS:
        if field not in payload or payload.get(field) in (None, ""):
            blockers.append(f"PHASE9_2_CHANGE_REQUEST_REQUIRED_FIELD_MISSING:{field}")
    for ack in CHANGE_REQUEST_REQUIRED_ACKS:
        if payload.get(ack) is not True:
            blockers.append(f"PHASE9_2_CHANGE_REQUEST_REQUIRED_ACK_MISSING:{ack}")
    if payload.get("source_phase9_2_runtime_authority_bridge_hash") in (None, "", "missing"):
        blockers.append("PHASE9_2_CHANGE_REQUEST_SOURCE_BRIDGE_HASH_MISSING")
    if payload.get("operator_runtime_authority_request_placeholder") in (None, ""):
        blockers.append("PHASE9_2_CHANGE_REQUEST_OPERATOR_REQUEST_PLACEHOLDER_MISSING")
    if payload.get("runtime_authority_change_request_approved") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_APPROVED_UNEXPECTED")
    if payload.get("runtime_authority_change_request_complete") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_COMPLETE_UNEXPECTED")
    if payload.get("runtime_authority_granted") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_RUNTIME_AUTHORITY_GRANTED_UNEXPECTED")
    if payload.get("secret_manager_runtime_binding_performed") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_SECRET_BINDING_PERFORMED_UNEXPECTED")
    if payload.get("signed_testnet_executor_enabled") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_EXECUTOR_ENABLED_UNEXPECTED")
    if payload.get("endpoint_policy_changed") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_ENDPOINT_POLICY_CHANGED_UNEXPECTED")
    if payload.get("phase9_2_order_submission_authorized") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_ORDER_SUBMISSION_AUTHORIZED_UNEXPECTED")
    if payload.get("single_order_runtime_scope") is not True:
        blockers.append("PHASE9_2_CHANGE_REQUEST_SINGLE_ORDER_SCOPE_MISSING")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("PHASE9_2_CHANGE_REQUEST_MAX_ORDER_COUNT_NOT_ONE")
    try:
        max_notional = float(payload.get("small_max_notional_usd"))
    except (TypeError, ValueError):
        max_notional = 0.0
        blockers.append("PHASE9_2_CHANGE_REQUEST_MAX_NOTIONAL_INVALID")
    if max_notional <= 0 or max_notional > 10.0:
        blockers.append("PHASE9_2_CHANGE_REQUEST_MAX_NOTIONAL_EXCEEDS_SMALL_CAP")
    if payload.get("kill_switch_runtime_confirmation_required") is not True:
        blockers.append("PHASE9_2_CHANGE_REQUEST_KILL_SWITCH_CONFIRMATION_NOT_REQUIRED")
    if payload.get("metadata_only_testnet_key_fingerprint_required") is not True:
        blockers.append("PHASE9_2_CHANGE_REQUEST_TESTNET_KEY_FINGERPRINT_NOT_REQUIRED")
    if payload.get("mainnet_key_scope_allowed") is not False:
        blockers.append("PHASE9_2_CHANGE_REQUEST_MAINNET_KEY_SCOPE_ALLOWED_UNEXPECTED")
    for field in ("order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created", "actual_order_submission_performed"):
        if payload.get(field) is not False:
            blockers.append(f"PHASE9_2_CHANGE_REQUEST_UNSAFE_FIELD:{field}")
    if unsafe:
        blockers.append("PHASE9_2_CHANGE_REQUEST_UNSAFE_FLAGS:" + ",".join(unsafe))
    if secret_like_values:
        blockers.append("PHASE9_2_CHANGE_REQUEST_SECRET_LIKE_VALUES_PRESENT:" + ",".join(secret_like_values))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_runtime_authority_change_request_validation_report",
        "phase9_2_runtime_authority_change_request_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "secret_like_value_paths": secret_like_values,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def build_phase9_2_runtime_authority_change_request_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_runtime_authority_bridge_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_runtime_authority_bridge_first:
        persist_phase9_2_runtime_authority_bridge_report(cfg=cfg, run_real_submit_gate_first=True)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    evidence_ready = not missing and not not_ready and not unsafe

    bridge_report = sources.get("phase9_2_runtime_authority_bridge_report", {})
    bridge_artifact = sources.get("phase9_2_runtime_authority_bridge_artifact", {})
    source_bridge_id = str(bridge_report.get("phase9_2_runtime_authority_bridge_id") or "missing_phase9_2_runtime_authority_bridge_id")
    source_bridge_hash = _artifact_hash(bridge_artifact) or _artifact_hash(bridge_report) or "missing"

    template = {
        "artifact_type": "phase9_2_runtime_authority_change_request_template_review_only",
        "phase9_2_runtime_authority_change_request_version": PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VERSION,
        "change_request_id": stable_id(
            "phase9_2_runtime_authority_change_request_template",
            {"source_bridge_id": source_bridge_id, "source_bridge_hash": source_bridge_hash, "created_at_utc": created},
            24,
        ),
        "review_only": True,
        "still_disabled": True,
        "source_phase9_2_runtime_authority_bridge_id": source_bridge_id,
        "source_phase9_2_runtime_authority_bridge_hash": source_bridge_hash,
        "source_ref": {
            "phase9_2_runtime_authority_bridge_report": "storage/latest/phase9_2_runtime_authority_bridge_report.json",
            "runtime_authority_bridge_artifact": "storage/latest/runtime_authority_bridge_STILL_DISABLED_REVIEW_ONLY.json",
        },
        "source_evidence_hash_summary": source_summary,
        "operator_runtime_authority_request_placeholder": "OPERATOR_MUST_FILL_REAL_RUNTIME_AUTHORITY_REQUEST_NOT_FIXTURE",
        "operator_signature_placeholder": "OPERATOR_SIGNATURE_REQUIRED_BEFORE_ANY_RUNTIME_AUTHORITY_REVIEW",
        "operator_change_ticket_placeholder": "OPERATOR_CHANGE_TICKET_OR_RECORD_ID_REQUIRED",
        "secret_manager_runtime_binding_request": {
            "requested": True,
            "metadata_only": True,
            "secret_values_forbidden": True,
            "runtime_binding_performed": False,
        },
        "fresh_preorder_risk_gate_refresh_request": {
            "requested": True,
            "must_run_immediately_before_endpoint_time": True,
            "performed_for_actual_endpoint_time": False,
        },
        "signed_testnet_executor_enablement_policy_change_request": {
            "requested": True,
            "executor_enablement_performed": False,
            "signed_testnet_executor_enabled": False,
        },
        "order_endpoint_policy_change_request": {
            "requested": True,
            "endpoint_policy_changed": False,
            "scope": "single_signed_testnet_order_only",
        },
        "single_order_runtime_scope": True,
        "max_order_count": 1,
        "small_max_notional_usd": 10.0,
        "daily_loss_cap_usd": 15.0,
        "kill_switch_runtime_confirmation_required": True,
        "metadata_only_testnet_key_fingerprint_required": True,
        "mainnet_key_scope_allowed": False,
        "ack_fixture_approval_is_not_runtime_authority": True,
        "ack_no_secret_values_in_request": True,
        "ack_runtime_secret_binding_not_performed": True,
        "ack_executor_still_disabled": True,
        "ack_endpoint_policy_not_changed": True,
        "ack_order_submission_still_disabled": True,
        "runtime_authority_change_request_approved": False,
        "runtime_authority_change_request_complete": False,
        "runtime_authority_change_applied": False,
        "runtime_authority_granted": False,
        "runtime_authority_bridge_complete": False,
        "secret_manager_runtime_binding_performed": False,
        "runtime_key_value_loaded": False,
        "runtime_api_secret_loaded": False,
        "runtime_private_key_loaded": False,
        "signed_testnet_executor_enabled": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "endpoint_policy_changed": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "real_order_id": None,
        "real_order_id_created": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "remaining_change_request_blockers": REMAINING_CHANGE_REQUEST_BLOCKERS,
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    template["phase9_2_runtime_authority_change_request_template_sha256"] = sha256_json(template)
    validation_report = validate_phase9_2_runtime_authority_change_request(template)
    negative_fixture_results = _build_negative_fixture_results(template)

    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_CHANGE_REQUEST_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_CHANGE_REQUEST_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_CHANGE_REQUEST_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers.extend(REMAINING_CHANGE_REQUEST_BLOCKERS)
    recorded = evidence_ready and validation_report["phase9_2_runtime_authority_change_request_valid"] and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]
    status = STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED if recorded else STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_BLOCKED_REVIEW_ONLY
    report = {
        "phase9_2_runtime_authority_change_request_id": template["change_request_id"],
        "phase9_2_runtime_authority_change_request_version": PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_runtime_authority_change_request_recorded": recorded,
        "runtime_authority_change_request_template_ready_for_manual_review": evidence_ready,
        "runtime_authority_change_request_approved": False,
        "runtime_authority_change_request_complete": False,
        "runtime_authority_granted": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "validation_report": validation_report,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers + validation_report.get("block_reasons", []))),
        "recommended_next_action": "manual_review_of_runtime_authority_change_request_template_without_secret_values_or_endpoint_calls",
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
    report["phase9_2_runtime_authority_change_request_report_sha256"] = sha256_json(report)
    return report, template, validation_report, negative_fixture_results


def _build_negative_fixture_results(template: Mapping[str, Any]) -> dict[str, Any]:
    cases = {
        "missing_source_bridge_hash": {"source_phase9_2_runtime_authority_bridge_hash": ""},
        "runtime_authority_change_request_approved_true": {"runtime_authority_change_request_approved": True},
        "runtime_authority_granted_true": {"runtime_authority_granted": True},
        "secret_manager_runtime_binding_performed_true": {"secret_manager_runtime_binding_performed": True},
        "signed_testnet_executor_enabled_true": {"signed_testnet_executor_enabled": True},
        "endpoint_policy_changed_true": {"endpoint_policy_changed": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "raw_secret_value_present": {"api_secret": "raw-secret-value-should-block"},
        "missing_operator_change_ticket": {"operator_change_ticket_placeholder": ""},
        "max_order_count_gt_one": {"max_order_count": 2},
        "mainnet_key_scope_allowed": {"mainnet_key_scope_allowed": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(template)
        payload.update(patch)
        validation = validate_phase9_2_runtime_authority_change_request(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_runtime_authority_change_request_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Runtime Authority Change Request Template - Still Disabled",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact prepares a review-only change request template for the future runtime authority boundary. It does not approve runtime authority, bind secrets, enable executors, change endpoint policy, create signatures, send HTTP, or submit orders.",
            "",
            "## Result",
            "",
            f"- Template ready for manual review: `{report.get('runtime_authority_change_request_template_ready_for_manual_review')}`",
            f"- Change request approved: `{report.get('runtime_authority_change_request_approved')}`",
            f"- Runtime authority granted: `{report.get('runtime_authority_granted')}`",
            f"- Phase 9.2 order submission authorized: `{report.get('phase9_2_order_submission_authorized')}`",
            "",
            "## Required Manual Fields Before Any Future Runtime Review",
            "",
            "- Real operator runtime authority request",
            "- Operator signature",
            "- Operator change ticket or record id",
            "- Metadata-only testnet key fingerprint reference",
            "- Fresh PreOrderRiskGate refresh at actual endpoint time",
            "- Separate executor policy approval",
            "- Separate endpoint policy approval constrained to one small testnet order",
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


def persist_phase9_2_runtime_authority_change_request_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_runtime_authority_bridge_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_runtime_authority_change_request")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, validation_report, negative_fixture_results = build_phase9_2_runtime_authority_change_request_report(
        cfg=cfg,
        run_runtime_authority_bridge_first=run_runtime_authority_bridge_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_runtime_authority_change_request_report.json", report)
        atomic_write_json(base / "runtime_authority_change_request_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json", template)
        atomic_write_json(base / "phase9_2_runtime_authority_change_request_validation_report.json", validation_report)
        atomic_write_json(base / "phase9_2_runtime_authority_change_request_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_REGISTRY_NAME),
        {
            "phase9_2_runtime_authority_change_request_id": report.get("phase9_2_runtime_authority_change_request_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "runtime_authority_change_request_recorded": report.get("phase9_2_runtime_authority_change_request_recorded"),
            "runtime_authority_change_request_approved": False,
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
        registry_name=PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_REGISTRY_NAME,
        id_field="phase9_2_runtime_authority_change_request_registry_record_id",
        hash_field="phase9_2_runtime_authority_change_request_registry_record_sha256",
        id_prefix="phase9_2_runtime_authority_change_request_registry_record",
    )
    atomic_write_json(latest / "phase9_2_runtime_authority_change_request_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_runtime_authority_change_request_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VERSION",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_BLOCKED_REVIEW_ONLY",
    "CHANGE_REQUEST_REQUIRED_FIELDS",
    "REMAINING_CHANGE_REQUEST_BLOCKERS",
    "build_phase9_2_runtime_authority_change_request_report",
    "persist_phase9_2_runtime_authority_change_request_report",
    "validate_phase9_2_runtime_authority_change_request",
]
