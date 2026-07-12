from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_submit_guard_recheck import (
    STATUS_RECHECK_READY_REVIEW_ONLY,
    persist_phase9_2_submit_guard_recheck_report,
)

PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_VERSION = "phase9_2_blocked_executor_wrapper_v1"
PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_REGISTRY_NAME = "phase9_2_blocked_executor_wrapper_registry"
STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY = "PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_EXECUTOR_WRAPPER_BLOCKED_REVIEW_ONLY = "PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_FILES = {
    "phase9_2_submit_guard_recheck_report": "phase9_2_submit_guard_recheck_after_operator_fixture_report.json",
    "phase9_2_submit_guard_recheck_artifact": "single_testnet_order_submit_guard_recheck_REVIEW_ONLY.json",
    "phase9_1_operator_supplied_approval_fixture": "phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json",
    "phase8_3_hot_path_preorder_risk_gate": "hot_path_preorder_risk_gate_review_only.json",
}

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase9_2_order_submission_authorized",
    "phase9_2_single_testnet_order_submit_may_begin",
    "phase9_order_submission_authorized",
    "order_submission_authorized",
    "executor_enabled",
    "executor_called",
    "submit_function_invoked",
    "phase9_3_status_polling_may_begin",
    "status_polling_started",
    "cancel_endpoint_called",
]

REQUIRED_WRAPPER_BLOCKERS = [
    "PHASE9_2_ORDER_ENDPOINT_CALLS_DISABLED_BY_DESIGN",
    "PHASE9_2_SIGNATURE_CREATION_DISABLED_BY_DESIGN",
    "PHASE9_2_HTTP_TRANSMISSION_DISABLED_BY_DESIGN",
    "PHASE9_2_OPERATOR_APPROVAL_IS_FIXTURE_ONLY_NOT_RUNTIME_AUTHORITY",
    "PHASE9_2_FRESH_PREORDER_RISK_GATE_REFRESH_REQUIRED_IMMEDIATELY_BEFORE_REAL_SUBMIT",
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
        "phase9_2_blocked_executor_wrapper_report_sha256",
        "phase9_2_blocked_executor_wrapper_artifact_sha256",
        "phase9_2_submit_guard_recheck_report_sha256",
        "phase9_2_submit_guard_recheck_artifact_sha256",
        "phase9_1_operator_supplied_approval_fixture_sha256",
        "hot_path_preorder_risk_gate_sha256",
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


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "phase9_2_submit_guard_recheck_report":
        return (
            data.get("status") == STATUS_RECHECK_READY_REVIEW_ONLY
            and data.get("phase9_2_submit_guard_recheck_ready") is True
            and data.get("phase9_2_pre_submit_conditions_ready_for_review_only") is True
            and data.get("phase9_2_order_submission_authorized") is False
            and data.get("phase9_3_status_polling_may_begin") is False
        )
    if name == "phase9_2_submit_guard_recheck_artifact":
        return (
            data.get("artifact_type") == "phase9_2_single_testnet_order_submit_guard_recheck_review_only"
            and data.get("phase9_2_pre_submit_conditions_ready_for_review_only") is True
            and data.get("phase9_2_order_submission_authorized") is False
            and data.get("order_endpoint_called") is False
            and data.get("http_request_sent") is False
            and data.get("signature_created") is False
        )
    if name == "phase9_1_operator_supplied_approval_fixture":
        return (
            data.get("artifact_type") == "phase9_1_operator_supplied_approval_fixture_review_only"
            and data.get("operator_supplied_fixture_only") is True
            and data.get("fixture_not_actual_runtime_approval") is True
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "phase8_3_hot_path_preorder_risk_gate":
        return (
            data.get("gate_type") == "phase8_3_hot_path_preorder_risk_gate_review_only"
            and data.get("no_order_endpoint_calls") is True
            and data.get("pre_submit_order_allowed") is False
        )
    return True


def validate_phase9_2_blocked_executor_wrapper(wrapper: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(wrapper or {})
    unsafe = _unsafe_fields(payload)
    blockers: list[str] = []
    if payload.get("artifact_type") != "phase9_2_blocked_executor_wrapper_review_only":
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_TYPE_INVALID")
    if payload.get("executor_wrapper_mode") != "blocked_dry_run_no_endpoint":
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_MODE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_NOT_REVIEW_ONLY")
    if payload.get("blocked_executor_wrapper_recorded") is not True:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_NOT_RECORDED")
    if payload.get("order_endpoint_called") is not False:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_ORDER_ENDPOINT_CALLED")
    if payload.get("http_request_sent") is not False:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_HTTP_SENT")
    if payload.get("signature_created") is not False:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_SIGNATURE_CREATED")
    if payload.get("actual_order_submission_performed") is not False:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_ACTUAL_SUBMISSION_PERFORMED")
    if payload.get("phase9_2_order_submission_authorized") is not False:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_SUBMISSION_AUTHORIZED")
    if payload.get("phase9_3_status_polling_may_begin") is not False:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_PHASE9_3_OPENED_WITHOUT_ORDER_ID")
    if not payload.get("idempotency_key_preview"):
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_IDEMPOTENCY_PREVIEW_MISSING")
    if payload.get("idempotency_key_is_preview_only") is not True:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_IDEMPOTENCY_NOT_PREVIEW_ONLY")
    remaining = payload.get("remaining_real_submit_blockers") or []
    for required in REQUIRED_WRAPPER_BLOCKERS:
        if required not in remaining:
            blockers.append(f"PHASE9_2_BLOCKED_EXECUTOR_REQUIRED_BLOCKER_MISSING:{required}")
    if unsafe:
        blockers.append("PHASE9_2_BLOCKED_EXECUTOR_UNSAFE_FLAGS:" + ",".join(unsafe))
    valid = not blockers
    return {
        "artifact_type": "phase9_2_blocked_executor_wrapper_validation_report",
        "phase9_2_blocked_executor_wrapper_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "unsafe_truthy_fields": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        **_flag_false_payload(),
    }


def build_phase9_2_blocked_executor_wrapper_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_submit_guard_recheck_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_submit_guard_recheck_first:
        persist_phase9_2_submit_guard_recheck_report(cfg=cfg, run_operator_fixture_first=True)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    blockers: list[str] = []
    blockers.extend(f"MISSING_PHASE9_2_BLOCKED_EXECUTOR_REQUIRED_EVIDENCE:{name}" for name in missing)
    blockers.extend(f"PHASE9_2_BLOCKED_EXECUTOR_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in not_ready)
    blockers.extend(f"UNSAFE_PHASE9_2_BLOCKED_EXECUTOR_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items())
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers

    recheck = sources.get("phase9_2_submit_guard_recheck_artifact", {})
    canonical_id_chain = dict(recheck.get("canonical_id_chain") or {})
    idempotency_key_preview = str(recheck.get("idempotency_key_preview") or stable_id("phase9_2_blocked_executor_idempotency_preview", source_summary, 24))
    wrapper = {
        "artifact_type": "phase9_2_blocked_executor_wrapper_review_only",
        "phase9_2_blocked_executor_wrapper_version": PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_VERSION,
        "executor_wrapper_mode": "blocked_dry_run_no_endpoint",
        "review_only": True,
        "fixture_only": True,
        "blocked_executor_wrapper_recorded": ready,
        "source_evidence_hash_summary": source_summary,
        "canonical_id_chain": canonical_id_chain,
        "idempotency_key_preview": idempotency_key_preview,
        "idempotency_key_is_preview_only": True,
        "client_order_id_preview": idempotency_key_preview,
        "dry_order_payload_preview": {
            "symbol": "BTCUSDT",
            "side": "UNSET_REVIEW_ONLY_FIXTURE",
            "order_type": "UNSET_REVIEW_ONLY_FIXTURE",
            "notional_cap": str((recheck.get("dry_order_payload_preview") or {}).get("notional_cap") or "5.0"),
            "client_order_id_preview": idempotency_key_preview,
            "complete_id_chain_required": True,
            "no_signature_created": True,
            "no_http_request_sent": True,
            "no_order_endpoint_called": True,
        },
        "executor_interface_invoked": False,
        "executor_enabled": False,
        "submit_function_invoked": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_3_status_polling_may_begin": False,
        "no_real_order_id_created": True,
        "real_order_id": None,
        "remaining_real_submit_blockers": REQUIRED_WRAPPER_BLOCKERS,
        **_flag_false_payload(),
        "created_at_utc": created,
    }
    wrapper["phase9_2_blocked_executor_wrapper_artifact_sha256"] = sha256_json(wrapper)
    validation_report = validate_phase9_2_blocked_executor_wrapper(wrapper)
    negative_fixture_results = _build_negative_fixture_results(wrapper)
    status = (
        STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY
        if ready and validation_report["phase9_2_blocked_executor_wrapper_valid"] and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]
        else STATUS_BLOCKED_EXECUTOR_WRAPPER_BLOCKED_REVIEW_ONLY
    )
    report = {
        "phase9_2_blocked_executor_wrapper_id": stable_id(
            "phase9_2_blocked_executor_wrapper",
            {"source_summary": source_summary, "wrapper_hash": sha256_json(wrapper), "blockers": blockers, "created_at_utc": created},
            24,
        ),
        "phase9_2_blocked_executor_wrapper_version": PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_VERSION,
        "status": status,
        "blocked": status != STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY,
        "fail_closed": status != STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY,
        "review_only": True,
        "fixture_only": True,
        "phase9_2_blocked_executor_wrapper_recorded": status == STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY,
        "phase9_2_dry_run_executor_wrapper_ready_review_only": status == STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY,
        "phase9_2_order_submission_authorized": False,
        "phase9_3_status_polling_may_begin": False,
        "no_real_order_id_created": True,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe,
        "validation_report": validation_report,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": blockers + validation_report.get("block_reasons", []),
        "recommended_next_action": "build_phase9_3_status_polling_cancel_handling_design_without_real_order_id",
        **_flag_false_payload(),
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_2_blocked_executor_wrapper_report_sha256"] = sha256_json(report)
    return report, wrapper, validation_report, negative_fixture_results


def _build_negative_fixture_results(wrapper: Mapping[str, Any]) -> dict[str, Any]:
    cases = {
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "http_request_sent_true": {"http_request_sent": True},
        "signature_created_true": {"signature_created": True},
        "executor_enabled_true": {"executor_enabled": True},
        "submission_authorized_true": {"phase9_2_order_submission_authorized": True},
        "status_polling_started_without_order_id": {"phase9_3_status_polling_may_begin": True},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(wrapper)
        payload.update(patch)
        validation = validate_phase9_2_blocked_executor_wrapper(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_2_blocked_executor_wrapper_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.2 Blocked Executor Wrapper - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact advances Phase 9.2 by recording a blocked executor wrapper around the single-testnet-order path. It intentionally does not create a signature, send HTTP, call an order endpoint, or create a real order id.",
            "",
            "## Result",
            "",
            f"- Wrapper recorded: `{report.get('phase9_2_blocked_executor_wrapper_recorded')}`",
            f"- Order submission authorized: `{report.get('phase9_2_order_submission_authorized')}`",
            f"- Phase 9.3 status polling may begin: `{report.get('phase9_3_status_polling_may_begin')}`",
            f"- No real order id created: `{report.get('no_real_order_id_created')}`",
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


def persist_phase9_2_blocked_executor_wrapper_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_submit_guard_recheck_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_2_single_testnet_order_submit")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, wrapper, validation_report, negative_fixture_results = build_phase9_2_blocked_executor_wrapper_report(
        cfg=cfg,
        run_submit_guard_recheck_first=run_submit_guard_recheck_first,
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_2_blocked_executor_wrapper_report.json", report)
        atomic_write_json(base / "single_testnet_order_BLOCKED_EXECUTOR_WRAPPER_REVIEW_ONLY.json", wrapper)
        atomic_write_json(base / "phase9_2_blocked_executor_wrapper_validation_report.json", validation_report)
        atomic_write_json(base / "phase9_2_blocked_executor_wrapper_negative_fixture_results.json", negative_fixture_results)
        (base / "PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_REGISTRY_NAME),
        {
            "phase9_2_blocked_executor_wrapper_id": report.get("phase9_2_blocked_executor_wrapper_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase9_2_blocked_executor_wrapper_recorded": report.get("phase9_2_blocked_executor_wrapper_recorded"),
            "phase9_2_order_submission_authorized": False,
            "phase9_3_status_polling_may_begin": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "actual_order_submission_performed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_REGISTRY_NAME,
        id_field="phase9_2_blocked_executor_wrapper_registry_record_id",
        hash_field="phase9_2_blocked_executor_wrapper_registry_record_sha256",
        id_prefix="phase9_2_blocked_executor_wrapper_registry_record",
    )
    atomic_write_json(latest / "phase9_2_blocked_executor_wrapper_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_2_blocked_executor_wrapper_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_VERSION",
    "STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_EXECUTOR_WRAPPER_BLOCKED_REVIEW_ONLY",
    "build_phase9_2_blocked_executor_wrapper_report",
    "persist_phase9_2_blocked_executor_wrapper_report",
    "validate_phase9_2_blocked_executor_wrapper",
]
