from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.validation.phase9_2_closure_packet import FALSE_FLAGS, persist_phase9_2_closure_packet

PHASE9_3_BOUNDARY_VERSION = "phase9_3_status_polling_cancel_boundary_v1"
STATUS_PHASE9_3_BOUNDARY_READY = "PHASE9_3_STATUS_POLLING_CANCEL_BOUNDARY_READY_NO_ENDPOINT_CALL_REVIEW_ONLY"
STATUS_PHASE9_3_BOUNDARY_BLOCKED = "PHASE9_3_STATUS_POLLING_CANCEL_BOUNDARY_BLOCKED_FAIL_CLOSED"


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
    return sorted([flag for flag in FALSE_FLAGS if _truthy(payload.get(flag))] + [flag for flag in ["status_polling_started", "real_order_id_available", "order_status_polling_authorized", "cancel_authorized"] if _truthy(payload.get(flag))])


def build_phase9_3_status_polling_cancel_boundary(root: Path | str = Path("."), *, run_closure_first: bool = True) -> dict[str, Any]:
    root = Path(root).resolve()
    latest = _latest(root)
    if run_closure_first:
        closure = persist_phase9_2_closure_packet(root)
    else:
        closure = _read(latest / "phase9_2_closure_packet_report.json")
    created = _utc_now()
    blockers: list[str] = []
    unsafe = _unsafe_true_flags(closure)
    if not closure:
        blockers.append("PHASE9_3_BOUNDARY_PHASE9_2_CLOSURE_REPORT_MISSING")
    if unsafe:
        blockers.append("PHASE9_3_BOUNDARY_UNSAFE_PHASE9_2_CLOSURE_FLAGS:" + ",".join(unsafe))
    if closure.get("ready_for_phase9_3_boundary_review_only") is not True:
        blockers.append("PHASE9_3_BOUNDARY_PHASE9_2_NOT_CLOSED_FOR_BOUNDARY_REVIEW")
    if closure.get("phase9_2_closed_review_only") is not True:
        blockers.append("PHASE9_3_BOUNDARY_PHASE9_2_CLOSURE_NOT_READY")
    if _truthy(closure.get("real_testnet_submit_may_begin")):
        blockers.append("PHASE9_3_BOUNDARY_REAL_SUBMIT_UNLOCKED_UNEXPECTED")

    ready = not blockers
    report: dict[str, Any] = {
        "artifact_type": "phase9_3_status_polling_cancel_boundary_review_only",
        "phase9_3_status_polling_cancel_boundary_version": PHASE9_3_BOUNDARY_VERSION,
        "status": STATUS_PHASE9_3_BOUNDARY_READY if ready else STATUS_PHASE9_3_BOUNDARY_BLOCKED,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "no_endpoint_call": True,
        "no_order_submit": True,
        "phase9_2_closure_report_sha256": _sha256(closure) if closure else None,
        "phase9_2_closure_status": closure.get("status"),
        "phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only": ready,
        "real_phase9_3_status_polling_may_begin": False,
        "phase9_3_status_polling_may_begin": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        "requires_real_phase9_2_testnet_order_id_before_real_status_polling": True,
        "requires_post_order_status_polling_authorization": True,
        "requires_cancel_guard_before_cancel_endpoint": True,
        "real_order_id": None,
        "real_order_id_available": False,
        "status_polling_started": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "private_account_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "status_model_review_only": [
            "submitted_or_acknowledged",
            "accepted",
            "rejected",
            "partially_filled",
            "filled",
            "cancel_requested",
            "cancelled",
            "expired_or_unknown",
            "final_status_for_phase9_4_reconciliation",
        ],
        "cancel_handling_boundary_review_only": {
            "cancel_requires_real_order_id": True,
            "cancel_requires_operator_cancel_intent": True,
            "cancel_requires_fresh_risk_or_kill_switch_context": True,
            "cancel_endpoint_remains_disabled_in_this_artifact": True,
        },
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "created_at_utc": created,
        **{flag: False for flag in FALSE_FLAGS},
    }
    report["phase9_3_status_polling_cancel_boundary_sha256"] = _sha256(report)
    return report


def persist_phase9_3_status_polling_cancel_boundary(root: Path | str = Path("."), *, run_closure_first: bool = True) -> dict[str, Any]:
    root = Path(root).resolve()
    latest = _latest(root)
    phase_dir = root / "storage" / "phase9_3_status_polling_cancel_boundary"
    signed_dir = root / "storage" / "signed_testnet"
    report = build_phase9_3_status_polling_cancel_boundary(root, run_closure_first=run_closure_first)
    handoff = "\n".join([
        "# Phase 9.3 Status Polling & Cancel Boundary / Review Only",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This packet opens only the Phase 9.3 design boundary after Phase 9.2 review closure. It does not poll status, call cancel, sign requests, or submit orders.",
        "",
        f"- phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only: `{report.get('phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only')}`",
        f"- real_phase9_3_status_polling_may_begin: `{report.get('real_phase9_3_status_polling_may_begin')}`",
        f"- order_status_endpoint_called: `{report.get('order_status_endpoint_called')}`",
        f"- cancel_endpoint_called: `{report.get('cancel_endpoint_called')}`",
    ])
    for base in (latest, phase_dir, signed_dir):
        base.mkdir(parents=True, exist_ok=True)
        _write(base / "phase9_3_status_polling_cancel_boundary_report.json", report)
        (base / "PHASE9_3_STATUS_POLLING_CANCEL_BOUNDARY_HANDOFF_NO_ENDPOINT_CALL_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    return report


__all__ = [
    "PHASE9_3_BOUNDARY_VERSION",
    "STATUS_PHASE9_3_BOUNDARY_READY",
    "STATUS_PHASE9_3_BOUNDARY_BLOCKED",
    "build_phase9_3_status_polling_cancel_boundary",
    "persist_phase9_3_status_polling_cancel_boundary",
]
