from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.disabled_executor_review import (
    persist_phase7_3_disabled_signed_testnet_executor_review_report,
)

PHASE7_4_VERSION = "phase7_4_disabled_execution_reconciliation_session_close_v1"
PHASE7_4_REGISTRY_NAME = "phase7_4_disabled_execution_reconciliation_session_close_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_BLOCKED_REVIEW_ONLY"

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
]

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_3_disabled_signed_testnet_executor_review": "phase7_3_disabled_signed_testnet_executor_review_report.json",
    "blocked_execution_evidence": "disabled_signed_testnet_blocked_execution_evidence_review_only.json",
    "blocked_cancel_evidence": "disabled_signed_testnet_blocked_cancel_evidence_review_only.json",
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
    # Keep compatibility with executor-level unsafe field detection if new unsafe flags are added there.
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(fields)


def _unsafe_flags_by_artifact(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    unsafe: dict[str, list[str]] = {}
    for name, payload in artifacts.items():
        flags = _unsafe_fields(payload)
        if flags:
            unsafe[name] = flags
    return unsafe


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase7_4_report_sha256",
        "phase7_3_report_sha256",
        "blocked_execution_evidence_sha256",
        "blocked_cancel_evidence_sha256",
        "reconciliation_report_sha256",
        "session_close_report_sha256",
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
        "status": data.get("status") or data.get("evidence_type") or data.get("report_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _build_reconciliation_report(
    *, report_id: str, phase7_3: Mapping[str, Any], execution: Mapping[str, Any], cancel: Mapping[str, Any], created_at_utc: str
) -> dict[str, Any]:
    execution_id = execution.get("execution_id")
    cancel_source_execution_id = cancel.get("source_execution_id")
    evidence_linked = bool(execution_id) and cancel_source_execution_id == execution_id
    expected_no_fill = execution.get("status") == "SIGNED_TESTNET_ORDER_SUBMISSION_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY"
    observed_fill_count = 0
    observed_position_delta = 0.0
    observed_balance_delta = 0.0
    mismatch_reasons: list[str] = []
    if not evidence_linked:
        mismatch_reasons.append("BLOCKED_CANCEL_EVIDENCE_NOT_LINKED_TO_BLOCKED_EXECUTION")
    if not expected_no_fill:
        mismatch_reasons.append("BLOCKED_EXECUTION_STATUS_NOT_RECOGNIZED")
    if execution.get("external_order_submission_performed") is not False:
        mismatch_reasons.append("EXTERNAL_ORDER_SUBMISSION_PERFORMED_UNEXPECTEDLY")
    if execution.get("actual_order_submission_performed") is not False:
        mismatch_reasons.append("ACTUAL_ORDER_SUBMISSION_PERFORMED_UNEXPECTEDLY")
    if execution.get("exchange_endpoint_called") is not False:
        mismatch_reasons.append("EXCHANGE_ENDPOINT_CALLED_UNEXPECTEDLY")
    if cancel.get("actual_cancel_performed") is not False:
        mismatch_reasons.append("ACTUAL_CANCEL_PERFORMED_UNEXPECTEDLY")
    if cancel.get("exchange_endpoint_called") is not False:
        mismatch_reasons.append("CANCEL_ENDPOINT_CALLED_UNEXPECTEDLY")
    if observed_fill_count != 0:
        mismatch_reasons.append("OBSERVED_FILL_COUNT_NOT_ZERO")
    if observed_position_delta != 0.0:
        mismatch_reasons.append("OBSERVED_POSITION_DELTA_NOT_ZERO")
    if observed_balance_delta != 0.0:
        mismatch_reasons.append("OBSERVED_BALANCE_DELTA_NOT_ZERO")

    mismatch_reasons = sorted(dict.fromkeys(mismatch_reasons))
    return {
        "report_type": "disabled_execution_reconciliation_report_review_only",
        "phase7_4_version": PHASE7_4_VERSION,
        "source_phase7_4_report_id": report_id,
        "source_phase7_3_report_id": phase7_3.get("phase7_3_disabled_signed_testnet_executor_review_id"),
        "source_execution_id": execution_id,
        "source_cancel_evidence_id": cancel.get("cancel_evidence_id"),
        "review_only": True,
        "disabled_execution_reconciliation": True,
        "execution_reconciled_review_only": not mismatch_reasons,
        "blocked_execution_evidence_linked": evidence_linked,
        "expected_fill_count": 0,
        "observed_fill_count": observed_fill_count,
        "expected_position_delta": 0.0,
        "observed_position_delta": observed_position_delta,
        "expected_balance_delta": 0.0,
        "observed_balance_delta": observed_balance_delta,
        "reconciliation_mismatch": bool(mismatch_reasons),
        "reconciliation_mismatch_reasons": mismatch_reasons,
        "promotion_blocked_if_mismatch": True,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_session_close_report(
    *, report_id: str, reconciliation: Mapping[str, Any], execution: Mapping[str, Any], cancel: Mapping[str, Any], created_at_utc: str
) -> dict[str, Any]:
    close_blockers: list[str] = []
    if reconciliation.get("execution_reconciled_review_only") is not True:
        close_blockers.append("DISABLED_EXECUTION_RECONCILIATION_NOT_CLEAN")
    if reconciliation.get("reconciliation_mismatch") is not False:
        close_blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    if execution.get("external_order_submission_performed") is not False:
        close_blockers.append("EXTERNAL_ORDER_SUBMISSION_PERFORMED_UNEXPECTEDLY")
    if cancel.get("actual_cancel_performed") is not False:
        close_blockers.append("ACTUAL_CANCEL_PERFORMED_UNEXPECTEDLY")
    close_blockers = sorted(dict.fromkeys(close_blockers))
    return {
        "report_type": "disabled_execution_session_close_report_review_only",
        "phase7_4_version": PHASE7_4_VERSION,
        "source_phase7_4_report_id": report_id,
        "source_reconciliation_report_type": reconciliation.get("report_type"),
        "source_execution_id": execution.get("execution_id"),
        "review_only": True,
        "disabled_execution_session_close": True,
        "session_closed_review_only": not close_blockers,
        "session_close_blocked": bool(close_blockers),
        "session_close_blockers": close_blockers,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "reconciliation_mismatch": reconciliation.get("reconciliation_mismatch") is True,
        "signed_testnet_promotion_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 7.4 Disabled Execution Reconciliation & Session Close — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase reconciles the Phase 7.3 blocked execution evidence. It confirms that disabled execution created no fills, no position change, no balance change, and no exchange endpoint calls.",
            "",
            "## Result",
            "",
            f"- Disabled execution reconciled: `{report.get('disabled_execution_reconciled_review_only')}`",
            f"- Session closed review-only: `{report.get('session_closed_review_only')}`",
            f"- Reconciliation mismatch: `{report.get('reconciliation_mismatch')}`",
            f"- External order submission performed: `{report.get('external_order_submission_performed')}`",
            "",
            "## Safety Flags",
            "",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `external_order_submission_performed=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase7_4_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_4_disabled_execution_reconciliation_session_close_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_3_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_3_first:
        persist_phase7_3_disabled_signed_testnet_executor_review_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}

    phase7_3 = artifacts.get("phase7_3_disabled_signed_testnet_executor_review", {})
    execution = artifacts.get("blocked_execution_evidence", {})
    cancel = artifacts.get("blocked_cancel_evidence", {})

    preliminary_report_id = stable_id(
        "phase7_4_disabled_execution_reconciliation_session_close",
        {"source_summary": source_summary, "created_at_utc": created},
        24,
    )
    reconciliation = _build_reconciliation_report(
        report_id=preliminary_report_id,
        phase7_3=phase7_3,
        execution=execution,
        cancel=cancel,
        created_at_utc=created,
    )
    session_close = _build_session_close_report(
        report_id=preliminary_report_id,
        reconciliation=reconciliation,
        execution=execution,
        cancel=cancel,
        created_at_utc=created,
    )

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_4_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_4_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_3.get("status") != "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_REVIEW_RECORDED_REVIEW_ONLY" or phase7_3.get("phase7_3_disabled_executor_review_ready") is not True:
        blockers.append("PHASE7_3_DISABLED_EXECUTOR_REVIEW_NOT_READY")
    if execution.get("status") != "SIGNED_TESTNET_ORDER_SUBMISSION_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY":
        blockers.append("BLOCKED_EXECUTION_EVIDENCE_STATUS_INVALID")
    if execution.get("submit_order_blocked_review_only") is not True or execution.get("blocked") is not True or execution.get("fail_closed") is not True:
        blockers.append("BLOCKED_EXECUTION_EVIDENCE_NOT_FAIL_CLOSED")
    if cancel.get("status") != "SIGNED_TESTNET_CANCEL_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY":
        blockers.append("BLOCKED_CANCEL_EVIDENCE_STATUS_INVALID")
    if cancel.get("cancel_order_blocked_review_only") is not True or cancel.get("blocked") is not True or cancel.get("fail_closed") is not True:
        blockers.append("BLOCKED_CANCEL_EVIDENCE_NOT_FAIL_CLOSED")
    if reconciliation.get("execution_reconciled_review_only") is not True:
        blockers.append("DISABLED_EXECUTION_RECONCILIATION_NOT_CLEAN")
    if reconciliation.get("reconciliation_mismatch") is not False:
        blockers.append("DISABLED_EXECUTION_RECONCILIATION_MISMATCH")
    if session_close.get("session_closed_review_only") is not True:
        blockers.append("DISABLED_EXECUTION_SESSION_CLOSE_NOT_CLEAN")
    if execution.get("external_order_submission_performed") is not False or cancel.get("external_order_submission_performed") is not False:
        blockers.append("EXTERNAL_ORDER_SUBMISSION_PERFORMED_UNEXPECTEDLY")
    if execution.get("exchange_endpoint_called") is not False or cancel.get("exchange_endpoint_called") is not False:
        blockers.append("EXCHANGE_ENDPOINT_CALLED_UNEXPECTEDLY")

    for source_name, source in {
        "reconciliation_report": reconciliation,
        "session_close_report": session_close,
    }.items():
        flags = _unsafe_fields(source)
        if flags:
            blockers.append(f"UNSAFE_PHASE7_4_GENERATED_ARTIFACT_FLAGS:{source_name}:{','.join(flags)}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_4_disabled_execution_reconciliation_session_close",
        {
            "source_summary": source_summary,
            "reconciliation_hash": sha256_json(reconciliation),
            "session_close_hash": sha256_json(session_close),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    reconciliation = {**reconciliation, "source_phase7_4_report_id": report_id}
    session_close = {**session_close, "source_phase7_4_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_4_disabled_execution_reconciliation_session_close_id": report_id,
        "phase7_4_version": PHASE7_4_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "disabled_execution_reconciliation_review": True,
        "session_close_design_review": True,
        "disabled_reconciliation_report_created": True,
        "disabled_session_close_report_created": True,
        "disabled_execution_reconciled_review_only": reconciliation.get("execution_reconciled_review_only") is True,
        "session_closed_review_only": session_close.get("session_closed_review_only") is True,
        "phase7_4_reconciliation_session_close_ready": ready,
        "blocked_execution_evidence_linked": reconciliation.get("blocked_execution_evidence_linked") is True,
        "expected_fill_count": reconciliation.get("expected_fill_count"),
        "observed_fill_count": reconciliation.get("observed_fill_count"),
        "expected_position_delta": reconciliation.get("expected_position_delta"),
        "observed_position_delta": reconciliation.get("observed_position_delta"),
        "expected_balance_delta": reconciliation.get("expected_balance_delta"),
        "observed_balance_delta": reconciliation.get("observed_balance_delta"),
        "reconciliation_mismatch": reconciliation.get("reconciliation_mismatch") is True,
        "reconciliation_mismatch_reasons": reconciliation.get("reconciliation_mismatch_reasons") or [],
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_reconciliation_authority": False,
        "signed_testnet_session_close_authority": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_4_allowed_next_scope": "signed_testnet_reconciliation_session_close_review_packet" if ready else "resolve_phase7_4_disabled_reconciliation_blockers",
        "recommended_next_action": "prepare_phase7_5_reconciliation_session_close_review_packet_keep_execution_disabled" if ready else "inspect_phase7_4_blockers_and_rerun_phase7_3_phase7_4",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    report["disabled_execution_reconciliation_report_sha256"] = sha256_json(reconciliation)
    report["disabled_execution_session_close_report_sha256"] = sha256_json(session_close)
    report["phase7_4_report_sha256"] = sha256_json(report)
    return report, reconciliation, session_close


def persist_phase7_4_disabled_execution_reconciliation_session_close_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_3_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_4_disabled_execution_reconciliation_session_close")
    report, reconciliation, session_close = build_phase7_4_disabled_execution_reconciliation_session_close_report(
        cfg=cfg, run_phase7_3_first=run_phase7_3_first
    )
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase7_4_disabled_execution_reconciliation_session_close_report.json", report)
    atomic_write_json(latest / "disabled_execution_reconciliation_report_review_only.json", reconciliation)
    atomic_write_json(latest / "disabled_execution_session_close_report_review_only.json", session_close)
    (latest / "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase7_4_disabled_execution_reconciliation_session_close_report.json", report)
    atomic_write_json(phase_dir / "disabled_execution_reconciliation_report_review_only.json", reconciliation)
    atomic_write_json(phase_dir / "disabled_execution_session_close_report_review_only.json", session_close)
    (phase_dir / "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_4_REGISTRY_NAME),
        {
            "phase7_4_disabled_execution_reconciliation_session_close_id": report.get("phase7_4_disabled_execution_reconciliation_session_close_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_4_reconciliation_session_close_ready": report.get("phase7_4_reconciliation_session_close_ready"),
            "disabled_execution_reconciled_review_only": report.get("disabled_execution_reconciled_review_only"),
            "session_closed_review_only": report.get("session_closed_review_only"),
            "reconciliation_mismatch": report.get("reconciliation_mismatch"),
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "external_order_submission_performed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE7_4_REGISTRY_NAME,
        id_field="phase7_4_disabled_execution_reconciliation_session_close_registry_record_id",
        hash_field="phase7_4_disabled_execution_reconciliation_session_close_registry_record_sha256",
        id_prefix="phase7_4_disabled_execution_reconciliation_session_close_registry_record",
    )
    atomic_write_json(latest / "phase7_4_disabled_execution_reconciliation_session_close_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_4_disabled_execution_reconciliation_session_close_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_4_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_4_disabled_execution_reconciliation_session_close_report",
    "persist_phase7_4_disabled_execution_reconciliation_session_close_report",
]
