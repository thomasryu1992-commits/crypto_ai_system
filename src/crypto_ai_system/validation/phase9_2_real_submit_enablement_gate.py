from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_blocked_executor_wrapper import (
    STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY,
    persist_phase9_2_blocked_executor_wrapper_report,
)
from crypto_ai_system.validation.phase9_3_status_polling_cancel_handling import (
    STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY,
    persist_phase9_3_status_polling_cancel_handling_report,
)

PHASE9_2_REAL_SUBMIT_GATE_VERSION = "phase9_2_real_submit_enablement_gate_v1"
PHASE9_2_REAL_SUBMIT_GATE_REGISTRY_NAME = "phase9_2_real_submit_enablement_gate_registry"
STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY = "PHASE9_2_REAL_SUBMIT_ENABLEMENT_GATE_RECORDED_BLOCKED_REVIEW_ONLY"
STATUS_PHASE9_2_REAL_SUBMIT_GATE_BLOCKED_REVIEW_ONLY = "PHASE9_2_REAL_SUBMIT_ENABLEMENT_GATE_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_FILES = {
    "phase8_4_final_guard_report": "phase8_4_signed_testnet_executor_final_guard_report.json",
    "phase8_3_hot_path_risk_gate_report": "phase8_3_hot_path_preorder_risk_gate_report.json",
    "phase9_1_operator_supplied_approval_fixture_validation": "phase9_1_operator_supplied_approval_fixture_validation_report.json",
    "phase9_1_operator_supplied_approval_fixture": "phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json",
    "phase9_2_submit_guard_recheck_report": "phase9_2_submit_guard_recheck_after_operator_fixture_report.json",
    "phase9_2_submit_guard_recheck_artifact": "single_testnet_order_submit_guard_recheck_REVIEW_ONLY.json",
    "phase9_2_blocked_executor_wrapper_report": "phase9_2_blocked_executor_wrapper_report.json",
    "phase9_2_blocked_executor_wrapper": "single_testnet_order_BLOCKED_EXECUTOR_WRAPPER_REVIEW_ONLY.json",
    "phase9_3_status_cancel_design_report": "phase9_3_status_polling_cancel_handling_report.json",
}

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_2_single_testnet_order_submit_may_begin",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "real_order_id_created",
    "real_order_id_present",
    "real_order_submit_attempted",
    "runtime_submit_gate_opened",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
]

REMAINING_REAL_SUBMIT_BLOCKERS = [
    "PHASE9_2_REAL_SUBMIT_REQUIRES_REAL_OPERATOR_APPROVAL_NOT_FIXTURE",
    "PHASE9_2_REAL_SUBMIT_REQUIRES_FRESH_PREORDER_RISK_GATE_IMMEDIATELY_BEFORE_ENDPOINT",
    "PHASE9_2_REAL_SUBMIT_REQUIRES_SIGNED_TESTNET_EXECUTOR_ENABLEMENT_NOT_PRESENT",
    "PHASE9_2_REAL_SUBMIT_REQUIRES_ORDER_ENDPOINT_POLICY_CHANGE_NOT_PRESENT",
    "PHASE9_2_REAL_SUBMIT_REQUIRES_SECRET_MANAGER_RUNTIME_BINDING_NOT_PRESENT",
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
        "phase9_2_real_submit_enablement_gate_report_sha256",
        "phase9_2_real_submit_enablement_gate_artifact_sha256",
        "phase9_3_status_polling_cancel_handling_report_sha256",
        "phase9_2_blocked_executor_wrapper_report_sha256",
        "phase9_2_submit_guard_recheck_report_sha256",
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
    if name == "phase8_4_final_guard_report":
        return data.get("phase8_4_signed_testnet_executor_final_guard_ready") is True and data.get("signed_order_executor_enabled") is False
    if name == "phase8_3_hot_path_risk_gate_report":
        return data.get("phase8_3_hot_path_risk_gate_ready") is True and data.get("phase8_4_final_guard_may_begin") is True
    if name == "phase9_1_operator_supplied_approval_fixture_validation":
        return data.get("fixture_valid_review_only") is True and data.get("fixture_values_complete_review_only") is True
    if name == "phase9_1_operator_supplied_approval_fixture":
        return (
            data.get("operator_decision") == "approve_single_signed_testnet_order"
            and data.get("operator_signature")
            and data.get("testnet_key_fingerprint_sha256")
            and data.get("kill_switch_confirmed_for_actual_approval") is True
            and data.get("fixture_not_actual_runtime_approval") is True
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase9_2_submit_guard_recheck_report":
        return data.get("phase9_2_submit_guard_recheck_ready") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_submit_guard_recheck_artifact":
        return data.get("phase9_2_pre_submit_conditions_ready_for_review_only") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "phase9_2_blocked_executor_wrapper_report":
        return data.get("status") == STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY and data.get("no_real_order_id_created") is True
    if name == "phase9_2_blocked_executor_wrapper":
        return data.get("artifact_type") == "phase9_2_blocked_executor_wrapper_review_only" and data.get("real_order_id") is None
    if name == "phase9_3_status_cancel_design_report":
        return data.get("status") == STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY and data.get("no_real_order_id_available") is True
    return True


def validate_phase9_2_real_submit_enablement_gate(gate: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(gate or {})
    unsafe = _unsafe_fields(payload)
    blockers: list[str] = []
    if payload.get("artifact_type") != "phase9_2_real_submit_enablement_gate_review_only":
        blockers.append("PHASE9_2_REAL_SUBMIT_GATE_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE9_2_REAL_SUBMIT_GATE_NOT_REVIEW_ONLY")
    if payload.get("blocked_final_runtime_gate") is not True:
        blockers.append("PHASE9_2_REAL_SUBMIT_GATE_NOT_BLOCKED_FINAL_GATE")
    if payload.get("phase9_2_real_submit_authorized") is not False:
        blockers.append("PHASE9_2_REAL_SUBMIT_AUTHORIZED_UNEXPECTED")
    if payload.get("phase9_2_order_submission_authorized") is not False:
        blockers.append("PHASE9_2_ORDER_SUBMISSION_AUTHORIZED_UNEXPECTED")
    if payload.get("phase9_3_status_polling_may_begin") is not False:
        blockers.append("PHASE9_2_OPENED_PHASE9_3_WITHOUT_REAL_ORDER_ID")
    if payload.get("real_order_id") is not None:
        blockers.append("PHASE9_2_REAL_ORDER_ID_PRESENT_UNEXPECTED")
    for field in ("order_endpoint_called", "http_request_sent", "signature_created", "signed_request_created", "actual_order_submission_performed"):
        if payload.get(field) is not False:
            blockers.append(f"PHASE9_2_REAL_SUBMIT_GATE_UNSAFE_FIELD:{field}")
    blockers_present = payload.get("remaining_real_submit_blockers") or []
    for required in REMAINING_REAL_SUBMIT_BLOCKERS:
        if required not in blockers_present:
            blockers.append(f"PHASE9_2_REAL_SUBMIT_GATE_REQUIRED_BLOCKER_MISSING:{required}")
    if unsafe:
        blockers.append("PHASE9_2_REAL_SUBMIT_GATE_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_real_submit_enablement_gate_validation_report",
        "phase9_2_real_submit_enablement_gate_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def build_phase9_2_real_submit_enablement_gate_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_3_design_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase9_3_design_first:
        persist_phase9_2_blocked_executor_wrapper_report(cfg=cfg, run_submit_guard_recheck_first=True)
        persist_phase9_3_status_polling_cancel_handling_report(cfg=cfg, run_phase9_2_blocked_wrapper_first=False)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_REAL_SUBMIT_GATE_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_REAL_SUBMIT_GATE_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_REAL_SUBMIT_GATE_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())

    preconditions_ready = not missing and not not_ready and not unsafe
    recheck = sources.get("phase9_2_submit_guard_recheck_artifact", {})
    wrapper = sources.get("phase9_2_blocked_executor_wrapper", {})
    gate = {
        "artifact_type": "phase9_2_real_submit_enablement_gate_review_only",
        "phase9_2_real_submit_enablement_gate_version": PHASE9_2_REAL_SUBMIT_GATE_VERSION,
        "review_only": True,
        "blocked_final_runtime_gate": True,
        "source_evidence_hash_summary": source_summary,
        "phase9_2_pre_submit_conditions_ready_for_review_only": preconditions_ready,
        "operator_approval_fixture_validated_review_only": _source_ready("phase9_1_operator_supplied_approval_fixture", sources.get("phase9_1_operator_supplied_approval_fixture", {})),
        "idempotency_key_preview": recheck.get("idempotency_key_preview") or wrapper.get("idempotency_key_preview"),
        "idempotency_key_is_preview_only": True,
        "dry_order_payload_preview": recheck.get("dry_order_payload_preview") or wrapper.get("dry_order_payload_preview"),
        "complete_id_chain_required_before_real_submit": True,
        "fresh_preorder_risk_gate_refresh_required_immediately_before_real_submit": True,
        "fixture_approval_is_not_runtime_authority": True,
        "real_order_id": None,
        "real_order_id_created": False,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "remaining_real_submit_blockers": REMAINING_REAL_SUBMIT_BLOCKERS,
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    gate["phase9_2_real_submit_enablement_gate_artifact_sha256"] = sha256_json(gate)
    validation_report = validate_phase9_2_real_submit_enablement_gate(gate)
    negative_fixture_results = _build_negative_fixture_results(gate)
    recorded = preconditions_ready and validation_report["phase9_2_real_submit_enablement_gate_valid"] and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]
    status = STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY if recorded else STATUS_PHASE9_2_REAL_SUBMIT_GATE_BLOCKED_REVIEW_ONLY
    blockers.extend(REMAINING_REAL_SUBMIT_BLOCKERS)
    report = {
        "phase9_2_real_submit_enablement_gate_id": stable_id(
            "phase9_2_real_submit_enablement_gate",
            {"source_summary": source_summary, "gate_hash": sha256_json(gate), "created_at_utc": created},
            24,
        ),
        "phase9_2_real_submit_enablement_gate_version": PHASE9_2_REAL_SUBMIT_GATE_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "phase9_2_real_submit_enablement_gate_recorded": recorded,
        "phase9_2_real_submit_preconditions_ready_for_manual_runtime_review": preconditions_ready,
        "phase9_2_real_submit_authorized": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "real_order_id_created": False,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "validation_report": validation_report,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers + validation_report.get("block_reasons", []))),
        "recommended_next_action": "do_not_submit_order_until_runtime_authority_secret_binding_fresh_risk_gate_and_endpoint_policy_are_explicitly_approved",
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
    report["phase9_2_real_submit_enablement_gate_report_sha256"] = sha256_json(report)
    return report, gate, validation_report, negative_fixture_results


def _build_negative_fixture_results(gate: Mapping[str, Any]) -> dict[str, Any]:
    cases = {
        "real_submit_authorized_true": {"phase9_2_real_submit_authorized": True},
        "order_submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "real_order_id_present": {"real_order_id": "testnet-order-id-not-allowed", "real_order_id_created": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "signature_created_true": {"signature_created": True},
        "http_request_sent_true": {"http_request_sent": True},
        "phase9_3_opened_true": {"phase9_3_status_polling_may_begin": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(gate)
        payload.update(patch)
        validation = validate_phase9_2_real_submit_enablement_gate(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_real_submit_enablement_gate_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Real Submit Enablement Gate - Blocked Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact adds the final real-submit enablement gate after the Phase 9.1 approval fixture, Phase 9.2 blocked wrapper, and Phase 9.3 status/cancel design. It does not submit an order, create a signature, send HTTP, or create a real order id.",
            "",
            "## Result",
            "",
            f"- Preconditions ready for manual runtime review: `{report.get('phase9_2_real_submit_preconditions_ready_for_manual_runtime_review')}`",
            f"- Real submit authorized: `{report.get('phase9_2_real_submit_authorized')}`",
            f"- Phase 9.3 status polling may begin: `{report.get('phase9_3_status_polling_may_begin')}`",
            f"- Real order id created: `{report.get('real_order_id_created')}`",
            "",
            "## Still Disabled",
            "",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "- `actual_order_submission_performed=false`",
            "",
        ]
    )


def persist_phase9_2_real_submit_enablement_gate_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_3_design_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_real_submit_enablement_gate")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, gate, validation_report, negative_fixture_results = build_phase9_2_real_submit_enablement_gate_report(
        cfg=cfg,
        run_phase9_3_design_first=run_phase9_3_design_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_real_submit_enablement_gate_report.json", report)
        atomic_write_json(base / "real_submit_enablement_gate_BLOCKED_REVIEW_ONLY.json", gate)
        atomic_write_json(base / "phase9_2_real_submit_enablement_gate_validation_report.json", validation_report)
        atomic_write_json(base / "phase9_2_real_submit_enablement_gate_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_REAL_SUBMIT_ENABLEMENT_GATE_HANDOFF_BLOCKED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_REAL_SUBMIT_GATE_REGISTRY_NAME),
        {
            "phase9_2_real_submit_enablement_gate_id": report.get("phase9_2_real_submit_enablement_gate_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase9_2_real_submit_enablement_gate_recorded": report.get("phase9_2_real_submit_enablement_gate_recorded"),
            "phase9_2_real_submit_authorized": False,
            "phase9_2_order_submission_authorized": False,
            "phase9_3_status_polling_may_begin": False,
            "real_order_id_created": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_REAL_SUBMIT_GATE_REGISTRY_NAME,
        id_field="phase9_2_real_submit_enablement_gate_registry_record_id",
        hash_field="phase9_2_real_submit_enablement_gate_registry_record_sha256",
        id_prefix="phase9_2_real_submit_enablement_gate_registry_record",
    )
    atomic_write_json(latest / "phase9_2_real_submit_enablement_gate_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_real_submit_enablement_gate_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_REAL_SUBMIT_GATE_VERSION",
    "STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY",
    "STATUS_PHASE9_2_REAL_SUBMIT_GATE_BLOCKED_REVIEW_ONLY",
    "REMAINING_REAL_SUBMIT_BLOCKERS",
    "build_phase9_2_real_submit_enablement_gate_report",
    "persist_phase9_2_real_submit_enablement_gate_report",
    "validate_phase9_2_real_submit_enablement_gate",
]
