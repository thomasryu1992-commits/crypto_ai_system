from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.disabled_session_reconciliation import (
    persist_phase7_4_disabled_execution_reconciliation_session_close_report,
)

PHASE7_5_VERSION = "phase7_5_reconciliation_session_close_review_packet_v1"
PHASE7_5_REGISTRY_NAME = "phase7_5_reconciliation_session_close_review_packet_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"

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
    "phase7_4_disabled_execution_reconciliation_session_close": "phase7_4_disabled_execution_reconciliation_session_close_report.json",
    "disabled_execution_reconciliation_report": "disabled_execution_reconciliation_report_review_only.json",
    "disabled_execution_session_close_report": "disabled_execution_session_close_report_review_only.json",
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
        "phase7_5_report_sha256",
        "phase7_4_report_sha256",
        "disabled_execution_reconciliation_report_sha256",
        "disabled_execution_session_close_report_sha256",
        "reconciliation_session_close_review_packet_sha256",
        "promotion_guard_report_sha256",
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
        "status": data.get("status") or data.get("report_type") or data.get("packet_type") or data.get("guard_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _build_review_packet(
    *, report_id: str, phase7_4: Mapping[str, Any], reconciliation: Mapping[str, Any], session_close: Mapping[str, Any], created_at_utc: str
) -> dict[str, Any]:
    return {
        "packet_type": "signed_testnet_reconciliation_session_close_review_packet_review_only",
        "phase7_5_version": PHASE7_5_VERSION,
        "source_phase7_5_report_id": report_id,
        "source_phase7_4_report_id": phase7_4.get("phase7_4_disabled_execution_reconciliation_session_close_id"),
        "source_reconciliation_report_type": reconciliation.get("report_type"),
        "source_session_close_report_type": session_close.get("report_type"),
        "review_only": True,
        "reconciliation_session_close_review_only": True,
        "actual_reconciliation_authority": False,
        "actual_session_close_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "allowed_scope": [
            "disabled_execution_reconciliation_review",
            "disabled_execution_session_close_review",
            "mismatch_fail_closed_review",
            "operator_handoff_for_later_explicit_executor_review",
        ],
        "forbidden_scope": [
            "actual_signed_testnet_order_submission",
            "actual_order_reconciliation_against_exchange",
            "place_order_enablement",
            "cancel_order_enablement",
            "signed_executor_enablement",
            "api_key_value_access",
            "api_secret_value_access",
            "secret_file_read_or_creation",
            "settings_yaml_mutation",
            "runtime_score_weights_mutation",
            "automatic_promotion_to_signed_testnet_or_live",
        ],
        "reconciliation_summary": {
            "execution_reconciled_review_only": reconciliation.get("execution_reconciled_review_only") is True,
            "reconciliation_mismatch": reconciliation.get("reconciliation_mismatch") is True,
            "reconciliation_mismatch_reasons": reconciliation.get("reconciliation_mismatch_reasons") or [],
            "expected_fill_count": reconciliation.get("expected_fill_count"),
            "observed_fill_count": reconciliation.get("observed_fill_count"),
            "observed_position_delta": reconciliation.get("observed_position_delta"),
            "observed_balance_delta": reconciliation.get("observed_balance_delta"),
        },
        "session_close_summary": {
            "session_closed_review_only": session_close.get("session_closed_review_only") is True,
            "session_close_blocked": session_close.get("session_close_blocked") is True,
            "session_close_blockers": session_close.get("session_close_blockers") or [],
        },
        "promotion_guard_requirement": {
            "reconciliation_mismatch_blocks_promotion": True,
            "session_close_blocked_blocks_promotion": True,
            "any_order_submission_flag_blocks_promotion": True,
            "signed_testnet_promotion_allowed": False,
            "auto_promotion_allowed": False,
        },
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_promotion_guard(
    *, report_id: str, phase7_4: Mapping[str, Any], reconciliation: Mapping[str, Any], session_close: Mapping[str, Any], created_at_utc: str
) -> dict[str, Any]:
    guard_blockers: list[str] = []
    if phase7_4.get("phase7_4_reconciliation_session_close_ready") is not True:
        guard_blockers.append("PHASE7_4_RECONCILIATION_SESSION_CLOSE_NOT_READY")
    if reconciliation.get("reconciliation_mismatch") is not False:
        guard_blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    if reconciliation.get("execution_reconciled_review_only") is not True:
        guard_blockers.append("DISABLED_EXECUTION_NOT_RECONCILED")
    if session_close.get("session_closed_review_only") is not True:
        guard_blockers.append("SESSION_CLOSE_NOT_CLEAN")
    if phase7_4.get("external_order_submission_performed") is not False:
        guard_blockers.append("EXTERNAL_ORDER_SUBMISSION_PERFORMED_UNEXPECTEDLY")
    if phase7_4.get("exchange_endpoint_called") is not False:
        guard_blockers.append("EXCHANGE_ENDPOINT_CALLED_UNEXPECTEDLY")
    guard_blockers = sorted(dict.fromkeys(guard_blockers))
    return {
        "guard_type": "signed_testnet_reconciliation_session_close_promotion_guard_review_only",
        "phase7_5_version": PHASE7_5_VERSION,
        "source_phase7_5_report_id": report_id,
        "source_phase7_4_report_id": phase7_4.get("phase7_4_disabled_execution_reconciliation_session_close_id"),
        "review_only": True,
        "guard_passed": not guard_blockers,
        "guard_blocked": bool(guard_blockers),
        "guard_blockers": guard_blockers,
        "reconciliation_mismatch_blocks_promotion": True,
        "session_close_blocked_blocks_promotion": True,
        "signed_testnet_promotion_allowed": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
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
            "# Phase 7.5 Reconciliation / Session Close Review Packet — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase packages Phase 7.4 disabled reconciliation and session-close evidence for operator review. It does not reconcile against an exchange, submit orders, enable executors, or promote to signed testnet/live.",
            "",
            "## Result",
            "",
            f"- Review packet created: `{report.get('reconciliation_session_close_review_packet_created')}`",
            f"- Promotion guard passed: `{report.get('promotion_guard_passed')}`",
            f"- Reconciliation mismatch: `{report.get('reconciliation_mismatch')}`",
            f"- Session closed review-only: `{report.get('session_closed_review_only')}`",
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
            f"`{report.get('phase7_5_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_5_reconciliation_session_close_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_4_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_4_first:
        persist_phase7_4_disabled_execution_reconciliation_session_close_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}

    phase7_4 = artifacts.get("phase7_4_disabled_execution_reconciliation_session_close", {})
    reconciliation = artifacts.get("disabled_execution_reconciliation_report", {})
    session_close = artifacts.get("disabled_execution_session_close_report", {})
    preliminary_id = stable_id("phase7_5_reconciliation_session_close_review_packet", {"source_summary": source_summary, "created_at_utc": created}, 24)
    packet = _build_review_packet(
        report_id=preliminary_id,
        phase7_4=phase7_4,
        reconciliation=reconciliation,
        session_close=session_close,
        created_at_utc=created,
    )
    promotion_guard = _build_promotion_guard(
        report_id=preliminary_id,
        phase7_4=phase7_4,
        reconciliation=reconciliation,
        session_close=session_close,
        created_at_utc=created,
    )

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_5_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_5_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_4.get("status") != "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_RECORDED_REVIEW_ONLY" or phase7_4.get("phase7_4_reconciliation_session_close_ready") is not True:
        blockers.append("PHASE7_4_RECONCILIATION_SESSION_CLOSE_NOT_READY")
    if reconciliation.get("report_type") != "disabled_execution_reconciliation_report_review_only":
        blockers.append("DISABLED_EXECUTION_RECONCILIATION_REPORT_INVALID")
    if reconciliation.get("execution_reconciled_review_only") is not True:
        blockers.append("DISABLED_EXECUTION_RECONCILIATION_NOT_CLEAN")
    if reconciliation.get("reconciliation_mismatch") is not False:
        blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    if session_close.get("report_type") != "disabled_execution_session_close_report_review_only":
        blockers.append("DISABLED_EXECUTION_SESSION_CLOSE_REPORT_INVALID")
    if session_close.get("session_closed_review_only") is not True:
        blockers.append("DISABLED_EXECUTION_SESSION_CLOSE_NOT_CLEAN")
    if promotion_guard.get("guard_passed") is not True:
        blockers.extend(str(item) for item in (promotion_guard.get("guard_blockers") or []))
    for generated_name, generated in {"review_packet": packet, "promotion_guard": promotion_guard}.items():
        flags = _unsafe_fields(generated)
        if flags:
            blockers.append(f"UNSAFE_PHASE7_5_GENERATED_ARTIFACT_FLAGS:{generated_name}:{','.join(flags)}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_5_reconciliation_session_close_review_packet",
        {
            "source_summary": source_summary,
            "packet_hash": sha256_json(packet),
            "promotion_guard_hash": sha256_json(promotion_guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    packet = {**packet, "source_phase7_5_report_id": report_id}
    promotion_guard = {**promotion_guard, "source_phase7_5_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_5_reconciliation_session_close_review_packet_id": report_id,
        "phase7_5_version": PHASE7_5_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "reconciliation_session_close_review_packet": True,
        "reconciliation_session_close_review_packet_created": True,
        "promotion_guard_report_created": True,
        "phase7_5_review_packet_ready": ready,
        "phase7_4_reconciliation_session_close_ready": phase7_4.get("phase7_4_reconciliation_session_close_ready") is True,
        "disabled_execution_reconciled_review_only": reconciliation.get("execution_reconciled_review_only") is True,
        "session_closed_review_only": session_close.get("session_closed_review_only") is True,
        "reconciliation_mismatch": reconciliation.get("reconciliation_mismatch") is True,
        "reconciliation_mismatch_reasons": reconciliation.get("reconciliation_mismatch_reasons") or [],
        "promotion_guard_passed": promotion_guard.get("guard_passed") is True,
        "promotion_guard_blockers": promotion_guard.get("guard_blockers") or [],
        "observed_fill_count": reconciliation.get("observed_fill_count"),
        "observed_position_delta": reconciliation.get("observed_position_delta"),
        "observed_balance_delta": reconciliation.get("observed_balance_delta"),
        "actual_reconciliation_authority": False,
        "actual_session_close_authority": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_reconciliation_authority": False,
        "signed_testnet_session_close_authority": False,
        "signed_testnet_promotion_authority": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_5_allowed_next_scope": "disabled_signed_testnet_session_review_operator_handoff" if ready else "resolve_phase7_5_reconciliation_session_close_review_blockers",
        "recommended_next_action": "prepare_phase7_6_disabled_session_review_operator_handoff_keep_execution_disabled" if ready else "inspect_phase7_5_blockers_and_rerun_phase7_4_phase7_5",
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
    report["reconciliation_session_close_review_packet_sha256"] = sha256_json(packet)
    report["promotion_guard_report_sha256"] = sha256_json(promotion_guard)
    report["phase7_5_report_sha256"] = sha256_json(report)
    return report, packet, promotion_guard


def persist_phase7_5_reconciliation_session_close_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_4_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_5_reconciliation_session_close_review_packet")
    report, packet, promotion_guard = build_phase7_5_reconciliation_session_close_review_packet_report(cfg=cfg, run_phase7_4_first=run_phase7_4_first)
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase7_5_reconciliation_session_close_review_packet_report.json", report)
    atomic_write_json(latest / "signed_testnet_reconciliation_session_close_review_packet_review_only.json", packet)
    atomic_write_json(latest / "signed_testnet_reconciliation_session_close_promotion_guard_report.json", promotion_guard)
    (latest / "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase7_5_reconciliation_session_close_review_packet_report.json", report)
    atomic_write_json(phase_dir / "signed_testnet_reconciliation_session_close_review_packet_review_only.json", packet)
    atomic_write_json(phase_dir / "signed_testnet_reconciliation_session_close_promotion_guard_report.json", promotion_guard)
    (phase_dir / "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_5_REGISTRY_NAME),
        {
            "phase7_5_reconciliation_session_close_review_packet_id": report.get("phase7_5_reconciliation_session_close_review_packet_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_5_review_packet_ready": report.get("phase7_5_review_packet_ready"),
            "promotion_guard_passed": report.get("promotion_guard_passed"),
            "reconciliation_mismatch": report.get("reconciliation_mismatch"),
            "session_closed_review_only": report.get("session_closed_review_only"),
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
        registry_name=PHASE7_5_REGISTRY_NAME,
        id_field="phase7_5_reconciliation_session_close_review_packet_registry_record_id",
        hash_field="phase7_5_reconciliation_session_close_review_packet_registry_record_sha256",
        id_prefix="phase7_5_reconciliation_session_close_review_packet_registry_record",
    )
    atomic_write_json(latest / "phase7_5_reconciliation_session_close_review_packet_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_5_reconciliation_session_close_review_packet_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_5_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_5_reconciliation_session_close_review_packet_report",
    "persist_phase7_5_reconciliation_session_close_review_packet_report",
]
