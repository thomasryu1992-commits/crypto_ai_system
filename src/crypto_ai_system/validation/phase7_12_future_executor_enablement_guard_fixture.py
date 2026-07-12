from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_11_future_executor_enablement_design_review import (
    persist_phase7_11_future_executor_enablement_design_review_report,
)

PHASE7_12_VERSION = "phase7_12_future_executor_enablement_guard_fixture_v1"
PHASE7_12_REGISTRY_NAME = "phase7_12_future_executor_enablement_guard_fixture_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_12_FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_12_FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_11_enablement_design_report": "phase7_11_future_executor_enablement_design_review_report.json",
    "future_executor_enablement_design_packet": "future_signed_testnet_executor_enablement_design_packet_review_only.json",
    "future_executor_enablement_design_guard": "future_signed_testnet_executor_enablement_design_guard_report.json",
}

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

REQUIRED_GUARD_FIXTURE_FIELDS = [
    "fixture_type",
    "review_only",
    "guard_fixture_only",
    "source_phase7_11_report_id",
    "source_enablement_design_packet_hash",
    "source_enablement_design_guard_hash",
    "metadata_only_key_reference_required",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "manual_kill_switch_confirmation_required",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
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
        "phase7_12_report_sha256",
        "phase7_11_report_sha256",
        "future_executor_enablement_design_packet_sha256",
        "future_executor_enablement_design_guard_report_sha256",
        "future_executor_enablement_guard_valid_fixture_sha256",
        "future_executor_enablement_guard_fixture_guard_report_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("fixture_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def validate_enablement_guard_fixture(payload: Mapping[str, Any], *, max_testnet_notional_usd: float = 25.0) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_GUARD_FIXTURE_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_ENABLEMENT_GUARD_FIXTURE_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_ENABLEMENT_GUARD_FIXTURE_FLAGS:" + ",".join(unsafe))
    if data.get("review_only") is not True:
        blockers.append("ENABLEMENT_GUARD_FIXTURE_NOT_REVIEW_ONLY")
    if data.get("guard_fixture_only") is not True:
        blockers.append("ENABLEMENT_GUARD_FIXTURE_NOT_FIXTURE_ONLY")
    for field in (
        "metadata_only_key_reference_required",
        "fresh_pre_submit_payload_validation_required",
        "fresh_pre_order_risk_gate_recheck_required",
        "manual_kill_switch_confirmation_required",
        "hard_caps_rechecked",
        "pre_order_risk_gate_rechecked",
        "reconciliation_required_after_any_session",
        "session_close_report_required",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_ENABLEMENT_GUARD_CONFIRMATION_NOT_TRUE:{field}")
    try:
        notional = float(data.get("max_testnet_notional_usd", 0))
    except (TypeError, ValueError):
        blockers.append("MAX_TESTNET_NOTIONAL_NOT_NUMERIC")
    else:
        if notional <= 0:
            blockers.append("MAX_TESTNET_NOTIONAL_NOT_POSITIVE")
        if notional > max_testnet_notional_usd:
            blockers.append("MAX_TESTNET_NOTIONAL_EXCEEDS_GUARD_CAP")
    valid = not blockers
    return {
        "fixture_valid_review_only": valid,
        "fixture_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "fixture_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_valid_fixture(*, report_id: str, artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase7_11 = artifacts.get("phase7_11_enablement_design_report", {})
    design_packet = artifacts.get("future_executor_enablement_design_packet", {})
    design_guard = artifacts.get("future_executor_enablement_design_guard", {})
    fixture = {
        "fixture_type": "future_signed_testnet_executor_enablement_guard_valid_fixture_review_only",
        "phase7_12_version": PHASE7_12_VERSION,
        "source_phase7_12_report_id": report_id,
        "source_phase7_11_report_id": phase7_11.get("phase7_11_future_executor_enablement_design_review_id"),
        "review_only": True,
        "guard_fixture_only": True,
        "not_runtime_authority": True,
        "source_enablement_design_packet_hash": sha256_json(dict(design_packet or {})) if design_packet else None,
        "source_enablement_design_guard_hash": sha256_json(dict(design_guard or {})) if design_guard else None,
        "metadata_only_key_reference_required": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "hard_caps_rechecked": True,
        "pre_order_risk_gate_rechecked": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "max_testnet_notional_usd": 25.0,
        "max_testnet_order_count": 1,
        "max_testnet_daily_loss_usd": 10.0,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }
    fixture["future_executor_enablement_guard_valid_fixture_sha256"] = sha256_json(fixture)
    return fixture


def _build_invalid_fixtures(valid: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    base = dict(valid or {})
    variants: dict[str, dict[str, Any]] = {}
    missing = dict(base)
    missing.pop("source_enablement_design_packet_hash", None)
    missing["fixture_type"] = "future_signed_testnet_executor_enablement_guard_invalid_missing_design_hash_fixture_review_only"
    variants["invalid_missing_design_hash"] = missing
    unsafe = dict(base)
    unsafe["fixture_type"] = "future_signed_testnet_executor_enablement_guard_invalid_unsafe_executor_flag_fixture_review_only"
    unsafe["signed_order_executor_enabled"] = True
    unsafe["testnet_order_submission_allowed"] = True
    variants["invalid_unsafe_executor_flag"] = unsafe
    no_kill = dict(base)
    no_kill["fixture_type"] = "future_signed_testnet_executor_enablement_guard_invalid_kill_switch_not_confirmed_fixture_review_only"
    no_kill["manual_kill_switch_confirmation_required"] = False
    variants["invalid_kill_switch_not_confirmed"] = no_kill
    cap = dict(base)
    cap["fixture_type"] = "future_signed_testnet_executor_enablement_guard_invalid_hard_cap_exceeded_fixture_review_only"
    cap["max_testnet_notional_usd"] = 250000.0
    variants["invalid_hard_cap_exceeded"] = cap
    key = dict(base)
    key["fixture_type"] = "future_signed_testnet_executor_enablement_guard_invalid_metadata_key_not_required_fixture_review_only"
    key["metadata_only_key_reference_required"] = False
    variants["invalid_metadata_key_not_required"] = key
    return variants


def _build_fixture_guard(*, report_id: str, valid_fixture: Mapping[str, Any], invalid_results: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    valid_result = validate_enablement_guard_fixture(valid_fixture)
    invalid_blocked = all(result.get("fixture_blocked_fail_closed") is True for result in invalid_results.values())
    guard_passed = valid_result.get("fixture_valid_review_only") is True and invalid_blocked
    return {
        "guard_type": "future_signed_testnet_executor_enablement_guard_fixture_guard_review_only",
        "phase7_12_version": PHASE7_12_VERSION,
        "source_phase7_12_report_id": report_id,
        "review_only": True,
        "guard_fixture_validation_only": True,
        "guard_passed": guard_passed,
        "valid_fixture_validation": valid_result,
        "invalid_fixture_validation": dict(invalid_results),
        "invalid_fixtures_blocked_fail_closed": invalid_blocked,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
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
    return "\n".join([
        "# Phase 7.12 Future Executor Enablement Guard Fixture — Review Only",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This phase validates future executor enablement guard fixtures. It does not enable an executor and does not submit orders.",
        "",
        "## Result",
        "",
        f"- Guard fixture ready: `{report.get('phase7_12_guard_fixture_ready')}`",
        f"- Valid fixture passed: `{report.get('valid_enablement_guard_fixture_passed_review_only_validation')}`",
        f"- Invalid fixtures blocked: `{report.get('invalid_enablement_guard_fixtures_blocked_fail_closed')}`",
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
    ])


def build_phase7_12_future_executor_enablement_guard_fixture_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_11_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_11_first:
        persist_phase7_11_future_executor_enablement_design_review_report(cfg=cfg)
    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    phase7_11 = artifacts.get("phase7_11_enablement_design_report", {})
    design_packet = artifacts.get("future_executor_enablement_design_packet", {})
    design_guard = artifacts.get("future_executor_enablement_design_guard", {})
    preliminary_id = stable_id("phase7_12_future_executor_enablement_guard_fixture", {"source_summary": source_summary, "created_at_utc": created}, 24)
    valid_fixture = _build_valid_fixture(report_id=preliminary_id, artifacts=artifacts, created_at_utc=created)
    invalid_fixtures = _build_invalid_fixtures(valid_fixture)
    invalid_results = {name: validate_enablement_guard_fixture(payload) for name, payload in invalid_fixtures.items()}
    fixture_guard = _build_fixture_guard(report_id=preliminary_id, valid_fixture=valid_fixture, invalid_results=invalid_results, created_at_utc=created)
    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_12_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_12_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_11.get("status") != "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_DESIGN_REVIEW_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_11_ENABLEMENT_DESIGN_NOT_READY")
    if phase7_11.get("phase7_11_enablement_design_ready") is not True:
        blockers.append("PHASE7_11_ENABLEMENT_DESIGN_READY_FALSE")
    if design_packet.get("packet_type") != "future_signed_testnet_executor_enablement_design_packet_review_only":
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_DESIGN_PACKET_INVALID")
    if design_guard.get("guard_type") != "future_signed_testnet_executor_enablement_design_guard_review_only":
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_DESIGN_GUARD_INVALID")
    if design_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_DESIGN_GUARD_NOT_PASSED")
    if fixture_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_12_future_executor_enablement_guard_fixture",
        {"source_summary": source_summary, "valid_fixture_hash": sha256_json(valid_fixture), "guard_hash": sha256_json(fixture_guard), "blockers": blockers, "created_at_utc": created},
        24,
    )
    valid_fixture["source_phase7_12_report_id"] = report_id
    fixture_guard["source_phase7_12_report_id"] = report_id
    report: dict[str, Any] = {
        "phase7_12_future_executor_enablement_guard_fixture_id": report_id,
        "phase7_12_version": PHASE7_12_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "guard_fixture_only": True,
        "phase7_12_guard_fixture_ready": ready,
        "valid_enablement_guard_fixture_created": True,
        "invalid_enablement_guard_fixture_count": len(invalid_fixtures),
        "fixture_guard_report_created": True,
        "valid_enablement_guard_fixture_passed_review_only_validation": fixture_guard.get("valid_fixture_validation", {}).get("fixture_valid_review_only") is True,
        "invalid_enablement_guard_fixtures_blocked_fail_closed": fixture_guard.get("invalid_fixtures_blocked_fail_closed") is True,
        "enablement_guard_fixture_guard_passed": fixture_guard.get("guard_passed") is True,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_12_allowed_next_scope": "future_executor_enablement_review_packet_still_disabled" if ready else "resolve_phase7_12_guard_fixture_blockers",
        "recommended_next_action": "prepare_phase7_13_future_executor_enablement_review_packet_keep_execution_disabled" if ready else "inspect_phase7_12_blockers_and_rerun_phase7_11_phase7_12",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
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
    valid_fixture["future_executor_enablement_guard_valid_fixture_sha256"] = sha256_json(valid_fixture)
    fixture_guard["future_executor_enablement_guard_fixture_guard_report_sha256"] = sha256_json(fixture_guard)
    report["future_executor_enablement_guard_valid_fixture_sha256"] = valid_fixture["future_executor_enablement_guard_valid_fixture_sha256"]
    report["future_executor_enablement_guard_fixture_guard_report_sha256"] = fixture_guard["future_executor_enablement_guard_fixture_guard_report_sha256"]
    report["phase7_12_report_sha256"] = sha256_json(report)
    return report, valid_fixture, fixture_guard, invalid_fixtures


def persist_phase7_12_future_executor_enablement_guard_fixture_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_11_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_12_future_executor_enablement_guard_fixture")
    fixtures_dir = _storage_dir(cfg, "storage/signed_testnet/fixtures")
    report, valid_fixture, fixture_guard, invalid_fixtures = build_phase7_12_future_executor_enablement_guard_fixture_report(cfg=cfg, run_phase7_11_first=run_phase7_11_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_12_future_executor_enablement_guard_fixture_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_enablement_guard_valid_fixture_review_only.json", valid_fixture)
    atomic_write_json(latest / "future_signed_testnet_executor_enablement_guard_fixture_guard_report.json", fixture_guard)
    (latest / "PHASE7_12_FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(phase_dir / "phase7_12_future_executor_enablement_guard_fixture_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_enablement_guard_valid_fixture_review_only.json", valid_fixture)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_enablement_guard_fixture_guard_report.json", fixture_guard)
    (phase_dir / "PHASE7_12_FUTURE_EXECUTOR_ENABLEMENT_GUARD_FIXTURE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    for name, payload in invalid_fixtures.items():
        file_name = f"future_executor_enablement_guard_{name}_FIXTURE_REVIEW_ONLY.json"
        atomic_write_json(fixtures_dir / file_name, payload)
        atomic_write_json(phase_dir / file_name, payload)

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_12_REGISTRY_NAME),
        {
            "phase7_12_future_executor_enablement_guard_fixture_id": report.get("phase7_12_future_executor_enablement_guard_fixture_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_12_guard_fixture_ready": report.get("phase7_12_guard_fixture_ready"),
            "enablement_guard_fixture_guard_passed": report.get("enablement_guard_fixture_guard_passed"),
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
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
        registry_name=PHASE7_12_REGISTRY_NAME,
        id_field="phase7_12_future_executor_enablement_guard_fixture_registry_record_id",
        hash_field="phase7_12_future_executor_enablement_guard_fixture_registry_record_sha256",
        id_prefix="phase7_12_future_executor_enablement_guard_fixture_registry_record",
    )
    atomic_write_json(latest / "phase7_12_future_executor_enablement_guard_fixture_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_12_future_executor_enablement_guard_fixture_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_12_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "validate_enablement_guard_fixture",
    "build_phase7_12_future_executor_enablement_guard_fixture_report",
    "persist_phase7_12_future_executor_enablement_guard_fixture_report",
]
