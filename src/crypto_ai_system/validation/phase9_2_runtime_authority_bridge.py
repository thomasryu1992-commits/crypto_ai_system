from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_real_submit_enablement_gate import (
    STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY,
    persist_phase9_2_real_submit_enablement_gate_report,
)

PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_VERSION = "phase9_2_runtime_authority_bridge_v1"
PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_REGISTRY_NAME = "phase9_2_runtime_authority_bridge_registry"
STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED = "PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED_REVIEW_ONLY"
STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_BLOCKED_REVIEW_ONLY = "PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_FILES = {
    "phase9_2_real_submit_gate_report": "phase9_2_real_submit_enablement_gate_report.json",
    "phase9_2_real_submit_gate_artifact": "real_submit_enablement_gate_BLOCKED_REVIEW_ONLY.json",
    "phase9_2_real_submit_gate_validation": "phase9_2_real_submit_enablement_gate_validation_report.json",
    "phase8_4_final_guard_report": "phase8_4_signed_testnet_executor_final_guard_report.json",
    "phase8_3_hot_path_risk_gate_report": "phase8_3_hot_path_preorder_risk_gate_report.json",
    "phase9_1_operator_fixture_validation": "phase9_1_operator_supplied_approval_fixture_validation_report.json",
    "phase9_3_status_cancel_design_report": "phase9_3_status_polling_cancel_handling_report.json",
}

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "runtime_authority_granted",
    "runtime_authority_bridge_complete",
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_2_single_testnet_order_submit_may_begin",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
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
]

RUNTIME_AUTHORITY_REQUIREMENTS = [
    "REAL_OPERATOR_APPROVAL_NOT_FIXTURE",
    "RUNTIME_SECRET_MANAGER_BINDING_WITHOUT_SECRET_VALUE_EXPOSURE",
    "FRESH_PREORDER_RISK_GATE_REFRESH_IMMEDIATELY_BEFORE_ENDPOINT",
    "SIGNED_TESTNET_EXECUTOR_ENABLEMENT_POLICY_CHANGE",
    "ORDER_ENDPOINT_POLICY_CHANGE_WITH_SINGLE_ORDER_SCOPE",
    "IDEMPOTENCY_AND_DUPLICATE_SUBMIT_GUARD_AT_RUNTIME",
    "ONE_ORDER_HARD_CAP_AND_SMALL_NOTIONAL_ENFORCED_AT_RUNTIME",
    "STATUS_POLLING_AND_CANCEL_HANDLER_READY_AFTER_REAL_ORDER_ID",
]

REMAINING_RUNTIME_AUTHORITY_BLOCKERS = [
    "PHASE9_2_RUNTIME_AUTHORITY_REQUIRES_REAL_OPERATOR_APPROVAL_NOT_FIXTURE",
    "PHASE9_2_RUNTIME_AUTHORITY_REQUIRES_SECRET_MANAGER_RUNTIME_BINDING_NOT_PRESENT",
    "PHASE9_2_RUNTIME_AUTHORITY_REQUIRES_FRESH_RISK_GATE_AT_ENDPOINT_TIME",
    "PHASE9_2_RUNTIME_AUTHORITY_REQUIRES_EXECUTOR_ENABLEMENT_POLICY_CHANGE_NOT_PRESENT",
    "PHASE9_2_RUNTIME_AUTHORITY_REQUIRES_ORDER_ENDPOINT_POLICY_CHANGE_NOT_PRESENT",
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
        "phase9_2_runtime_authority_bridge_report_sha256",
        "phase9_2_runtime_authority_bridge_artifact_sha256",
        "phase9_2_real_submit_enablement_gate_report_sha256",
        "phase9_2_real_submit_enablement_gate_artifact_sha256",
        "phase9_3_status_polling_cancel_handling_report_sha256",
        "phase9_1_operator_supplied_approval_fixture_validation_report_sha256",
        "phase8_4_signed_testnet_executor_final_guard_report_sha256",
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
    if name == "phase9_2_real_submit_gate_report":
        return (
            data.get("status") == STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY
            and data.get("phase9_2_real_submit_preconditions_ready_for_manual_runtime_review") is True
            and data.get("phase9_2_real_submit_authorized") is False
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_2_real_submit_gate_artifact":
        return (
            data.get("artifact_type") == "phase9_2_real_submit_enablement_gate_review_only"
            and data.get("blocked_final_runtime_gate") is True
            and data.get("fixture_approval_is_not_runtime_authority") is True
            and data.get("phase9_2_real_submit_authorized") is False
            and data.get("real_order_id") is None
        )
    if name == "phase9_2_real_submit_gate_validation":
        return data.get("phase9_2_real_submit_enablement_gate_valid") is True
    if name == "phase8_4_final_guard_report":
        return data.get("phase8_4_signed_testnet_executor_final_guard_ready") is True and data.get("signed_order_executor_enabled") is False
    if name == "phase8_3_hot_path_risk_gate_report":
        return data.get("phase8_3_hot_path_risk_gate_ready") is True and data.get("phase8_4_final_guard_may_begin") is True
    if name == "phase9_1_operator_fixture_validation":
        return data.get("fixture_valid_review_only") is True and data.get("fixture_values_complete_review_only") is True
    if name == "phase9_3_status_cancel_design_report":
        return data.get("no_real_order_id_available") is True and data.get("phase9_4_testnet_reconciliation_may_begin") is False
    return True


def validate_phase9_2_runtime_authority_bridge(bridge: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(bridge or {})
    unsafe = _unsafe_fields(payload)
    blockers: list[str] = []
    if payload.get("artifact_type") != "phase9_2_runtime_authority_bridge_review_only":
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_NOT_REVIEW_ONLY")
    if payload.get("still_disabled") is not True:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_NOT_STILL_DISABLED")
    if payload.get("runtime_authority_granted") is not False:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_GRANTED_UNEXPECTED")
    if payload.get("runtime_authority_bridge_complete") is not False:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_COMPLETE_UNEXPECTED")
    if payload.get("phase9_2_order_submission_authorized") is not False:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_ORDER_SUBMISSION_AUTHORIZED_UNEXPECTED")
    if payload.get("secret_manager_runtime_binding_performed") is not False:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_SECRET_BINDING_PERFORMED_UNEXPECTED")
    if payload.get("signed_testnet_executor_enabled") is not False:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_EXECUTOR_ENABLED_UNEXPECTED")
    if payload.get("endpoint_policy_changed") is not False:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_ENDPOINT_POLICY_CHANGED_UNEXPECTED")
    for field in ("order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created", "actual_order_submission_performed"):
        if payload.get(field) is not False:
            blockers.append(f"PHASE9_2_RUNTIME_AUTHORITY_UNSAFE_FIELD:{field}")
    requirements = payload.get("runtime_authority_requirements") or []
    for required in RUNTIME_AUTHORITY_REQUIREMENTS:
        if required not in requirements:
            blockers.append(f"PHASE9_2_RUNTIME_AUTHORITY_REQUIRED_REQUIREMENT_MISSING:{required}")
    blockers_present = payload.get("remaining_runtime_authority_blockers") or []
    for required in REMAINING_RUNTIME_AUTHORITY_BLOCKERS:
        if required not in blockers_present:
            blockers.append(f"PHASE9_2_RUNTIME_AUTHORITY_REQUIRED_BLOCKER_MISSING:{required}")
    if unsafe:
        blockers.append("PHASE9_2_RUNTIME_AUTHORITY_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_runtime_authority_bridge_validation_report",
        "phase9_2_runtime_authority_bridge_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def build_phase9_2_runtime_authority_bridge_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_real_submit_gate_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_real_submit_gate_first:
        persist_phase9_2_real_submit_enablement_gate_report(cfg=cfg, run_phase9_3_design_first=True)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    evidence_ready = not missing and not not_ready and not unsafe

    bridge = {
        "artifact_type": "phase9_2_runtime_authority_bridge_review_only",
        "phase9_2_runtime_authority_bridge_version": PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_VERSION,
        "review_only": True,
        "still_disabled": True,
        "source_evidence_hash_summary": source_summary,
        "runtime_authority_requirements": RUNTIME_AUTHORITY_REQUIREMENTS,
        "runtime_authority_preconditions_ready_for_manual_design_review": evidence_ready,
        "runtime_authority_granted": False,
        "runtime_authority_bridge_complete": False,
        "runtime_authority_source": None,
        "operator_approval_fixture_is_not_runtime_authority": True,
        "real_operator_approval_required": True,
        "secret_manager_runtime_binding_required": True,
        "secret_manager_runtime_binding_performed": False,
        "runtime_secret_value_accessed": False,
        "runtime_key_value_loaded": False,
        "runtime_api_secret_loaded": False,
        "runtime_private_key_loaded": False,
        "fresh_preorder_risk_gate_refresh_required_immediately_before_endpoint": True,
        "fresh_preorder_risk_gate_refresh_performed_for_real_submit": False,
        "signed_testnet_executor_enablement_policy_change_required": True,
        "signed_testnet_executor_enabled": False,
        "endpoint_policy_change_required": True,
        "endpoint_policy_changed": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
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
        "remaining_runtime_authority_blockers": REMAINING_RUNTIME_AUTHORITY_BLOCKERS,
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    bridge["phase9_2_runtime_authority_bridge_artifact_sha256"] = sha256_json(bridge)
    validation_report = validate_phase9_2_runtime_authority_bridge(bridge)
    negative_fixture_results = _build_negative_fixture_results(bridge)
    recorded = evidence_ready and validation_report["phase9_2_runtime_authority_bridge_valid"] and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]
    status = STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED if recorded else STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_BLOCKED_REVIEW_ONLY
    blockers.extend(REMAINING_RUNTIME_AUTHORITY_BLOCKERS)
    report = {
        "phase9_2_runtime_authority_bridge_id": stable_id(
            "phase9_2_runtime_authority_bridge",
            {"source_summary": source_summary, "bridge_hash": sha256_json(bridge), "created_at_utc": created},
            24,
        ),
        "phase9_2_runtime_authority_bridge_version": PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "still_disabled": True,
        "phase9_2_runtime_authority_bridge_recorded": recorded,
        "runtime_authority_preconditions_ready_for_manual_design_review": evidence_ready,
        "runtime_authority_granted": False,
        "runtime_authority_bridge_complete": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "runtime_authority_requirements": RUNTIME_AUTHORITY_REQUIREMENTS,
        "validation_report": validation_report,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers + validation_report.get("block_reasons", []))),
        "recommended_next_action": "prepare_separate_runtime_authority_change_request_without_secret_values_or_endpoint_calls",
        **_flag_false_payload(),
        "signed_testnet_executor_enabled": False,
        "endpoint_policy_changed": False,
        "secret_manager_runtime_binding_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_2_runtime_authority_bridge_report_sha256"] = sha256_json(report)
    return report, bridge, validation_report, negative_fixture_results


def _build_negative_fixture_results(bridge: Mapping[str, Any]) -> dict[str, Any]:
    cases = {
        "runtime_authority_granted_true": {"runtime_authority_granted": True},
        "runtime_authority_bridge_complete_true": {"runtime_authority_bridge_complete": True},
        "secret_manager_runtime_binding_performed_true": {"secret_manager_runtime_binding_performed": True},
        "signed_testnet_executor_enabled_true": {"signed_testnet_executor_enabled": True},
        "endpoint_policy_changed_true": {"endpoint_policy_changed": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "signature_created_true": {"signature_created": True},
        "http_request_sent_true": {"http_request_sent": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "missing_runtime_authority_requirement": {"runtime_authority_requirements": RUNTIME_AUTHORITY_REQUIREMENTS[:-1]},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(bridge)
        payload.update(patch)
        validation = validate_phase9_2_runtime_authority_bridge(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_runtime_authority_bridge_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Runtime Authority Bridge - Still Disabled",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact defines the runtime authority boundary that would be required before any future real signed-testnet submit path. It is not runtime authority and does not bind secrets, enable executors, change endpoint policy, create signatures, send HTTP, or submit orders.",
            "",
            "## Result",
            "",
            f"- Evidence ready for manual design review: `{report.get('runtime_authority_preconditions_ready_for_manual_design_review')}`",
            f"- Runtime authority granted: `{report.get('runtime_authority_granted')}`",
            f"- Runtime authority bridge complete: `{report.get('runtime_authority_bridge_complete')}`",
            f"- Phase 9.2 order submission authorized: `{report.get('phase9_2_order_submission_authorized')}`",
            "",
            "## Required Future Authority Changes",
            "",
            "- Real operator approval, not fixture approval",
            "- Secret manager runtime binding without secret value exposure",
            "- Fresh PreOrderRiskGate refresh immediately before endpoint path",
            "- Signed testnet executor enablement policy change",
            "- Order endpoint policy change constrained to one small hard-capped testnet order",
            "",
            "## Still Disabled",
            "",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `secret_manager_runtime_binding_performed=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "- `actual_order_submission_performed=false`",
            "",
        ]
    )


def persist_phase9_2_runtime_authority_bridge_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_real_submit_gate_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_runtime_authority_bridge")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, bridge, validation_report, negative_fixture_results = build_phase9_2_runtime_authority_bridge_report(
        cfg=cfg,
        run_real_submit_gate_first=run_real_submit_gate_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_runtime_authority_bridge_report.json", report)
        atomic_write_json(base / "runtime_authority_bridge_STILL_DISABLED_REVIEW_ONLY.json", bridge)
        atomic_write_json(base / "phase9_2_runtime_authority_bridge_validation_report.json", validation_report)
        atomic_write_json(base / "phase9_2_runtime_authority_bridge_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_REGISTRY_NAME),
        {
            "phase9_2_runtime_authority_bridge_id": report.get("phase9_2_runtime_authority_bridge_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase9_2_runtime_authority_bridge_recorded": report.get("phase9_2_runtime_authority_bridge_recorded"),
            "runtime_authority_granted": False,
            "runtime_authority_bridge_complete": False,
            "phase9_2_order_submission_authorized": False,
            "phase9_3_status_polling_may_begin": False,
            "secret_manager_runtime_binding_performed": False,
            "signed_testnet_executor_enabled": False,
            "endpoint_policy_changed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_REGISTRY_NAME,
        id_field="phase9_2_runtime_authority_bridge_registry_record_id",
        hash_field="phase9_2_runtime_authority_bridge_registry_record_sha256",
        id_prefix="phase9_2_runtime_authority_bridge_registry_record",
    )
    atomic_write_json(latest / "phase9_2_runtime_authority_bridge_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_runtime_authority_bridge_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_VERSION",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED",
    "STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_BLOCKED_REVIEW_ONLY",
    "RUNTIME_AUTHORITY_REQUIREMENTS",
    "REMAINING_RUNTIME_AUTHORITY_BLOCKERS",
    "build_phase9_2_runtime_authority_bridge_report",
    "persist_phase9_2_runtime_authority_bridge_report",
    "validate_phase9_2_runtime_authority_bridge",
]
