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

PHASE9_3_STATUS_CANCEL_VERSION = "phase9_3_status_polling_cancel_handling_design_v1"
PHASE9_3_STATUS_CANCEL_REGISTRY_NAME = "phase9_3_status_polling_cancel_handling_registry"
STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY = "PHASE9_3_STATUS_POLLING_CANCEL_HANDLING_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY"
STATUS_PHASE9_3_DESIGN_BLOCKED_REVIEW_ONLY = "PHASE9_3_STATUS_POLLING_CANCEL_HANDLING_DESIGN_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_FILES = {
    "phase9_2_blocked_executor_wrapper_report": "phase9_2_blocked_executor_wrapper_report.json",
    "phase9_2_blocked_executor_wrapper": "single_testnet_order_BLOCKED_EXECUTOR_WRAPPER_REVIEW_ONLY.json",
    "phase9_2_blocked_executor_wrapper_validation": "phase9_2_blocked_executor_wrapper_validation_report.json",
}

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase9_2_order_submission_authorized",
    "phase9_3_status_polling_may_begin",
    "status_polling_started",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
]

STATUS_TRANSITION_MODEL = [
    "not_started_no_real_order_id",
    "submitted",
    "accepted",
    "rejected",
    "partial_fill",
    "full_fill",
    "cancel_requested",
    "cancel_accepted",
    "final_status",
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


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_3_status_polling_cancel_handling_report_sha256",
        "phase9_3_status_polling_cancel_handling_design_sha256",
        "phase9_2_blocked_executor_wrapper_report_sha256",
        "phase9_2_blocked_executor_wrapper_artifact_sha256",
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
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_2_blocked_executor_wrapper_report":
        return (
            data.get("status") == STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY
            and data.get("phase9_2_blocked_executor_wrapper_recorded") is True
            and data.get("phase9_2_order_submission_authorized") is False
            and data.get("phase9_3_status_polling_may_begin") is False
            and data.get("no_real_order_id_created") is True
        )
    if name == "phase9_2_blocked_executor_wrapper":
        return (
            data.get("artifact_type") == "phase9_2_blocked_executor_wrapper_review_only"
            and data.get("no_real_order_id_created") is True
            and data.get("real_order_id") is None
            and data.get("phase9_3_status_polling_may_begin") is False
        )
    if name == "phase9_2_blocked_executor_wrapper_validation":
        return data.get("phase9_2_blocked_executor_wrapper_valid") is True
    return True


def validate_phase9_3_status_polling_cancel_handling_design(design: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(design or {})
    unsafe = _unsafe_fields(payload)
    blockers: list[str] = []
    if payload.get("artifact_type") != "phase9_3_status_polling_cancel_handling_design_review_only":
        blockers.append("PHASE9_3_STATUS_CANCEL_DESIGN_TYPE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE9_3_STATUS_CANCEL_DESIGN_NOT_REVIEW_ONLY")
    if payload.get("no_real_order_id_available") is not True:
        blockers.append("PHASE9_3_STATUS_CANCEL_EXPECTED_NO_REAL_ORDER_ID")
    if payload.get("real_order_id") is not None:
        blockers.append("PHASE9_3_STATUS_CANCEL_REAL_ORDER_ID_PRESENT_UNEXPECTED")
    if payload.get("status_polling_started") is not False:
        blockers.append("PHASE9_3_STATUS_POLLING_STARTED_WITHOUT_REAL_ORDER")
    if payload.get("order_status_endpoint_called") is not False:
        blockers.append("PHASE9_3_ORDER_STATUS_ENDPOINT_CALLED")
    if payload.get("cancel_endpoint_called") is not False:
        blockers.append("PHASE9_3_CANCEL_ENDPOINT_CALLED")
    if payload.get("cancel_request_sent") is not False:
        blockers.append("PHASE9_3_CANCEL_REQUEST_SENT")
    if payload.get("phase9_4_testnet_reconciliation_may_begin") is not False:
        blockers.append("PHASE9_3_OPENED_RECONCILIATION_WITHOUT_FINAL_STATUS")
    transitions = payload.get("status_transition_model") or []
    for required in STATUS_TRANSITION_MODEL:
        if required not in transitions:
            blockers.append(f"PHASE9_3_STATUS_MODEL_MISSING:{required}")
    if unsafe:
        blockers.append("PHASE9_3_STATUS_CANCEL_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_3_status_polling_cancel_handling_design_validation_report",
        "phase9_3_status_polling_cancel_handling_design_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def build_phase9_3_status_polling_cancel_handling_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_2_blocked_wrapper_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase9_2_blocked_wrapper_first:
        persist_phase9_2_blocked_executor_wrapper_report(cfg=cfg, run_submit_guard_recheck_first=True)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_3_REQUIRED_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_3_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_3_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers.append("PHASE9_3_NO_REAL_ORDER_ID_AVAILABLE_STATUS_POLLING_BLOCKED_BY_DESIGN")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))

    wrapper = sources.get("phase9_2_blocked_executor_wrapper", {})
    design = {
        "artifact_type": "phase9_3_status_polling_cancel_handling_design_review_only",
        "phase9_3_status_polling_cancel_handling_version": PHASE9_3_STATUS_CANCEL_VERSION,
        "review_only": True,
        "blocked_design_artifact": True,
        "source_evidence_hash_summary": source_summary,
        "source_phase9_2_blocked_executor_wrapper_hash": _artifact_hash(wrapper),
        "no_real_order_id_available": True,
        "real_order_id": None,
        "order_id_source": "none_phase9_2_blocked_before_submit",
        "status_transition_model": STATUS_TRANSITION_MODEL,
        "status_polling_plan": {
            "submitted": "would_poll_exchange_order_status_after_real_phase9_2_submit",
            "accepted": "would_record_exchange_acceptance_timestamp_latency_and_response_code",
            "rejected": "would_record_normalized_rejection_reason_and_block_phase9_4_if_unexpected",
            "partial_fill": "would_record_cumulative_fill_price_qty_fee_and_remaining_qty",
            "full_fill": "would_record_final_fill_price_fee_slippage_latency",
            "cancel_requested": "would_require_explicit_cancel_guard_and_idempotency_key",
            "cancel_accepted": "would_record_cancel_acceptance_and_final_position_delta",
            "final_status": "would_finalize_status_before_reconciliation",
        },
        "cancel_handling_plan": {
            "cancel_requires_real_order_id": True,
            "cancel_requires_fresh_kill_switch_confirmation": True,
            "cancel_requires_idempotency_key": True,
            "cancel_endpoint_disabled_until_real_phase9_2_order_exists": True,
        },
        "latency_error_tracking_plan": {
            "api_latency_ms": "planned",
            "api_error_code": "planned",
            "rate_limit_response": "planned",
            "normalized_status": "planned",
        },
        "status_polling_started": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    design["phase9_3_status_polling_cancel_handling_design_sha256"] = sha256_json(design)
    validation_report = validate_phase9_3_status_polling_cancel_handling_design(design)
    negative_fixture_results = _build_negative_fixture_results(design)
    source_ready = not missing and not not_ready and not unsafe
    recorded = source_ready and validation_report["phase9_3_status_polling_cancel_handling_design_valid"] and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]
    status = STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY if recorded else STATUS_PHASE9_3_DESIGN_BLOCKED_REVIEW_ONLY
    report = {
        "phase9_3_status_polling_cancel_handling_id": stable_id(
            "phase9_3_status_polling_cancel_handling_design",
            {"source_summary": source_summary, "design_hash": sha256_json(design), "blockers": blockers, "created_at_utc": created},
            24,
        ),
        "phase9_3_status_polling_cancel_handling_version": PHASE9_3_STATUS_CANCEL_VERSION,
        "status": status,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "phase9_3_design_recorded": recorded,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "no_real_order_id_available": True,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "validation_report": validation_report,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": blockers + validation_report.get("block_reasons", []),
        "recommended_next_action": "only_begin_real_phase9_3_after_a_real_phase9_2_testnet_order_id_exists_and_status_polling_is_explicitly_authorized",
        **_flag_false_payload(),
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "http_request_sent": False,
        "signature_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_3_status_polling_cancel_handling_report_sha256"] = sha256_json(report)
    return report, design, validation_report, negative_fixture_results


def _build_negative_fixture_results(design: Mapping[str, Any]) -> dict[str, Any]:
    cases = {
        "real_order_id_present": {"real_order_id": "fixture-real-order-id-not-allowed", "no_real_order_id_available": False},
        "status_polling_started_true": {"status_polling_started": True},
        "order_status_endpoint_called_true": {"order_status_endpoint_called": True},
        "cancel_endpoint_called_true": {"cancel_endpoint_called": True},
        "cancel_request_sent_true": {"cancel_request_sent": True},
        "phase9_4_opened_without_final_status": {"phase9_4_testnet_reconciliation_may_begin": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(design)
        payload.update(patch)
        validation = validate_phase9_3_status_polling_cancel_handling_design(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_3_status_polling_cancel_handling_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.3 Status Polling and Cancel Handling Design - Blocked Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact designs the Phase 9.3 status polling and cancel handling state model, but it remains blocked because Phase 9.2 did not create a real exchange order id.",
            "",
            "## Result",
            "",
            f"- Design recorded: `{report.get('phase9_3_design_recorded')}`",
            f"- Status polling may begin: `{report.get('phase9_3_status_polling_may_begin')}`",
            f"- Phase 9.4 reconciliation may begin: `{report.get('phase9_4_testnet_reconciliation_may_begin')}`",
            f"- No real order id available: `{report.get('no_real_order_id_available')}`",
            "",
            "## Still Disabled",
            "",
            "- `order_status_endpoint_called=false`",
            "- `cancel_endpoint_called=false`",
            "- `cancel_request_sent=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "- `actual_order_submission_performed=false`",
            "",
        ]
    )


def persist_phase9_3_status_polling_cancel_handling_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_2_blocked_wrapper_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_3_status_polling_cancel_handling")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, design, validation_report, negative_fixture_results = build_phase9_3_status_polling_cancel_handling_report(
        cfg=cfg,
        run_phase9_2_blocked_wrapper_first=run_phase9_2_blocked_wrapper_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_3_status_polling_cancel_handling_report.json", report)
        atomic_write_json(base / "status_polling_cancel_handling_DESIGN_BLOCKED_REVIEW_ONLY.json", design)
        atomic_write_json(base / "phase9_3_status_polling_cancel_handling_validation_report.json", validation_report)
        atomic_write_json(base / "phase9_3_status_polling_cancel_handling_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_3_STATUS_POLLING_CANCEL_HANDLING_HANDOFF_BLOCKED_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_3_STATUS_CANCEL_REGISTRY_NAME),
        {
            "phase9_3_status_polling_cancel_handling_id": report.get("phase9_3_status_polling_cancel_handling_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase9_3_design_recorded": report.get("phase9_3_design_recorded"),
            "phase9_3_status_polling_may_begin": False,
            "phase9_4_testnet_reconciliation_may_begin": False,
            "no_real_order_id_available": True,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "cancel_request_sent": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_3_STATUS_CANCEL_REGISTRY_NAME,
        id_field="phase9_3_status_polling_cancel_handling_registry_record_id",
        hash_field="phase9_3_status_polling_cancel_handling_registry_record_sha256",
        id_prefix="phase9_3_status_polling_cancel_handling_registry_record",
    )
    atomic_write_json(latest / "phase9_3_status_polling_cancel_handling_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_3_status_polling_cancel_handling_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_3_STATUS_CANCEL_VERSION",
    "STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY",
    "STATUS_PHASE9_3_DESIGN_BLOCKED_REVIEW_ONLY",
    "build_phase9_3_status_polling_cancel_handling_report",
    "persist_phase9_3_status_polling_cancel_handling_report",
    "validate_phase9_3_status_polling_cancel_handling_design",
]
