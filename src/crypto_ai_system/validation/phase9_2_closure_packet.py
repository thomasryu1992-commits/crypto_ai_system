from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PHASE9_2_CLOSURE_VERSION = "phase9_2_closure_packet_v2"
STATUS_PHASE9_2_CLOSURE_READY = "PHASE9_2_CLOSURE_PACKET_READY_FOR_PHASE9_3_BOUNDARY_REVIEW_ONLY"
STATUS_PHASE9_2_CLOSURE_BLOCKED = "PHASE9_2_CLOSURE_PACKET_BLOCKED_FAIL_CLOSED"

FALSE_FLAGS = [
    "real_testnet_submit_may_begin",
    "phase9_2_order_submission_authorized",
    "phase9_2_single_order_runtime_submit_approval_granted",
    "actual_order_submission_performed",
    "external_order_submission_performed",
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
    "api_key_value_logged",
    "api_secret_value_logged",
    "secret_value_accessed",
    "executor_enable_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(_stable_json(data).encode("utf-8")).hexdigest()


def _latest(root: Path | str) -> Path:
    p = Path(root).resolve() / "storage" / "latest"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_true_flags(payload: Mapping[str, Any]) -> list[str]:
    return sorted([flag for flag in FALSE_FLAGS if _truthy(payload.get(flag))])


def _summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_name": name,
        "present": bool(payload),
        "status": payload.get("status"),
        "blocked": payload.get("blocked"),
        "fail_closed": payload.get("fail_closed"),
        "sha256": _sha256(payload) if payload else None,
    }


def build_phase9_2_closure_packet(root: Path | str = Path(".")) -> dict[str, Any]:
    latest = _latest(root)
    created = _utc_now()
    approval = _read(latest / "phase9_2_separate_one_order_runtime_submit_approval_packet_report.json")
    quick = _read(latest / "phase9_2_quick_one_order_approval_ready_check_report.json")
    checklist = _read(latest / "phase9_2_final_pre_submit_checklist_report.json")
    bridge = _read(latest / "phase9_2_public_metadata_probe_bridge_report.json")
    filled = _read(latest / "phase9_2_public_metadata_probe_result_filled_validation_report.json")

    sources = {
        "one_order_approval_packet": approval,
        "quick_one_order_ready_check": quick,
        "final_pre_submit_checklist": checklist,
        "public_metadata_probe_bridge": bridge,
        "public_metadata_filled_validation": filled,
    }
    blockers: list[str] = []
    for name, payload in sources.items():
        if not payload:
            blockers.append(f"PHASE9_2_CLOSURE_REQUIRED_REPORT_MISSING:{name}")
        unsafe = _unsafe_true_flags(payload)
        if unsafe:
            blockers.append(f"PHASE9_2_CLOSURE_UNSAFE_TRUE_FLAGS:{name}:{','.join(unsafe)}")

    # Phase 9.2 closure v2 intentionally distinguishes review-complete evidence
    # from runtime-only blockers that must remain unresolved until the actual
    # operator-local one-order submit action. Fresh hot-path risk refresh, local
    # secret binding, and local execution requirements are expected to remain as
    # action-time blockers and must not prevent review-only closure.
    approval_validated = (
        approval.get("operator_filled_approval_validated") is True
        or quick.get("operator_filled_approval_validated") is True
    )
    approval_ready = (
        approval.get("ready_for_one_order_runtime_submit_operator_review_only") is True
        or quick.get("ready_for_one_order_runtime_submit_operator_review_only") is True
    )
    metadata_ready = (
        approval.get("public_metadata_conditions_ready_for_submit_review_only") is True
        or quick.get("public_metadata_conditions_ready_for_submit_review_only") is True
        or bridge.get("public_metadata_conditions_ready_for_submit_review_only") is True
        or bridge.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True
    )
    checklist_ready_or_runtime_only = (
        checklist.get("ready_for_separate_one_order_runtime_approval_review_only") is True
        or quick.get("final_pre_submit_checklist_ready_for_separate_approval_review_only") is True
    )

    if not approval_validated:
        blockers.append("PHASE9_2_CLOSURE_OPERATOR_FILLED_ONE_ORDER_APPROVAL_NOT_VALIDATED")
    if not approval_ready:
        blockers.append("PHASE9_2_CLOSURE_ONE_ORDER_APPROVAL_NOT_READY_FOR_OPERATOR_REVIEW")
    if not metadata_ready:
        blockers.append("PHASE9_2_CLOSURE_PUBLIC_METADATA_CONDITIONS_NOT_READY_FOR_REVIEW_ONLY_CLOSURE")
    if not checklist_ready_or_runtime_only:
        blockers.append("PHASE9_2_CLOSURE_FINAL_PRE_SUBMIT_CHECKLIST_NOT_READY_FOR_SEPARATE_APPROVAL_REVIEW")
    if _truthy(approval.get("real_testnet_submit_may_begin")) or _truthy(quick.get("real_testnet_submit_may_begin")):
        blockers.append("PHASE9_2_CLOSURE_APPROVAL_REPORT_UNLOCKED_REAL_SUBMIT_UNEXPECTED")

    ready = not blockers
    report: dict[str, Any] = {
        "artifact_type": "phase9_2_closure_packet_review_only",
        "phase9_2_closure_version": PHASE9_2_CLOSURE_VERSION,
        "status": STATUS_PHASE9_2_CLOSURE_READY if ready else STATUS_PHASE9_2_CLOSURE_BLOCKED,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "no_order_submit": True,
        "phase9_2_closed_review_only": ready,
        "ready_for_phase9_3_boundary_review_only": ready,
        "phase9_2_completion_summary": {
            "public_metadata_probe_bridge_validated": metadata_ready,
            "final_pre_submit_checklist_ready_or_runtime_only_blockers_remaining": checklist_ready_or_runtime_only,
            "one_order_approval_packet_validated": approval_validated,
            "one_order_approval_ready_for_operator_review": approval_ready,
            "real_submit_still_locked": (approval.get("real_testnet_submit_may_begin") is False and quick.get("real_testnet_submit_may_begin") in {False, None}),
            "runtime_only_blockers_deferred_to_action_time": [
                "fresh_hot_path_risk_refresh_required_at_action_time",
                "runtime_secret_binding_required_at_action_time_metadata_only_in_artifacts",
                "operator_local_execution_required_for_any_real_testnet_submit",
            ],
        },
        "required_source_summary": {name: _summary(name, payload) for name, payload in sources.items()},
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "phase9_3_boundary_may_be_created": ready,
        "phase9_3_boundary_waits_for_real_post_submit_order_id": True,
        "phase9_3_real_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "operator_local_runtime_submit_still_required_before_real_phase9_3": True,
        "fresh_hot_path_risk_refresh_required_at_action_time": True,
        "runtime_secret_binding_required_at_action_time_metadata_only_in_artifacts": True,
        "post_submit_immediate_relock_required": True,
        "created_at_utc": created,
        **{flag: False for flag in FALSE_FLAGS},
    }
    report["phase9_2_closure_packet_sha256"] = _sha256(report)
    return report


def persist_phase9_2_closure_packet(root: Path | str = Path(".")) -> dict[str, Any]:
    root = Path(root).resolve()
    latest = _latest(root)
    phase_dir = root / "storage" / "phase9_2_closure_packet"
    signed_dir = root / "storage" / "signed_testnet"
    report = build_phase9_2_closure_packet(root)
    handoff = "\n".join([
        "# Phase 9.2 Closure Packet / Review Only",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This packet closes Phase 9.2 only as review evidence when public metadata, final pre-submit checklist, and one-order approval packet are valid.",
        "It does not submit orders, create signatures, call private endpoints, or unlock real testnet submission.",
        "",
        f"- phase9_2_closed_review_only: `{report.get('phase9_2_closed_review_only')}`",
        f"- ready_for_phase9_3_boundary_review_only: `{report.get('ready_for_phase9_3_boundary_review_only')}`",
        f"- real_testnet_submit_may_begin: `{report.get('real_testnet_submit_may_begin')}`",
        f"- phase9_3_real_status_polling_may_begin: `{report.get('phase9_3_real_status_polling_may_begin')}`",
    ])
    for base in (latest, phase_dir, signed_dir):
        base.mkdir(parents=True, exist_ok=True)
        _write(base / "phase9_2_closure_packet_report.json", report)
        (base / "PHASE9_2_CLOSURE_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    return report


__all__ = [
    "PHASE9_2_CLOSURE_VERSION",
    "STATUS_PHASE9_2_CLOSURE_READY",
    "STATUS_PHASE9_2_CLOSURE_BLOCKED",
    "build_phase9_2_closure_packet",
    "persist_phase9_2_closure_packet",
]
