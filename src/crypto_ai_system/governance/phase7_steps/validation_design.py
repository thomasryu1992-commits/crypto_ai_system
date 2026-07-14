from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE7_VERSION = "phase7_signed_testnet_validation_design_guard_v1"
PHASE7_REGISTRY_NAME = "phase7_signed_testnet_validation_design_guard_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_BLOCKED_REVIEW_ONLY"

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
    "live_trading_allowed",
    "auto_promotion_allowed",
]

REQUIRED_SOURCE_ARTIFACTS = {
    "phase6_6_actual_intake_validation_bridge": "phase6_6_actual_intake_validation_bridge_report.json",
    "phase7_entry_review_packet": "phase7_entry_review_packet_review_only.json",
    "phase6_signed_testnet_preparation_preview": "phase6_signed_testnet_preparation_preview_report.json",
    "signed_testnet_pre_submit_validation": "signed_testnet_pre_submit_validation_report.json",
    "signed_testnet_enablement_packet": "signed_testnet_execution_enablement_packet.json",
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
    return [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]


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
        "phase6_6_report_sha256",
        "phase6_preparation_preview_report_sha256",
        "pre_submit_validation_sha256",
        "enablement_packet_sha256",
        "phase7_entry_review_packet_sha256",
        "phase7_report_sha256",
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
        "status": data.get("status") or data.get("bridge_status"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _build_validation_design_packet(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet_type": "signed_testnet_validation_design_packet_review_only",
        "phase7_version": PHASE7_VERSION,
        "source_phase7_design_guard_id": report.get("phase7_signed_testnet_validation_design_guard_id"),
        "phase7_design_ready_review_only": report.get("phase7_design_ready_review_only"),
        "phase7_entry_review_possible_from_bridge": report.get("phase7_entry_review_possible_from_bridge"),
        "signed_testnet_validation_design_only": True,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "allowed_scope": [
            "testnet_order_lifecycle_design",
            "disabled_executor_guard_review",
            "pre_submit_payload_validation_plan",
            "idempotency_and_reconciliation_plan",
            "operator_handoff_for_later_executor_review",
        ],
        "forbidden_scope": [
            "actual_signed_testnet_order_submission",
            "place_order_enablement",
            "cancel_order_enablement",
            "signed_executor_enablement",
            "api_key_value_access",
            "api_secret_value_access",
            "secret_file_read_or_creation",
            "settings_yaml_mutation",
            "runtime_score_weights_mutation",
            "automatic_promotion_to_live",
        ],
        "order_lifecycle_checklist": [
            "Generate idempotency key before any future order request.",
            "Run PreOrderRiskGate immediately before any future signed testnet executor review.",
            "Validate symbol, side, quantity, notional, min/max notional, fee/slippage assumptions, and risk caps.",
            "Require submit/cancel/fill/position sync/balance/margin/leverage evidence in a future Phase 7 executor stage.",
            "Require reconciliation and session close report after every future signed testnet session.",
        ],
        "pre_submit_payload_validation_plan": {
            "required_fields": ["symbol", "side", "order_type", "quantity", "notional", "time_in_force", "idempotency_key"],
            "blocked_if": [
                "missing_id_chain",
                "stale_data",
                "fallback_or_synthetic_source",
                "approval_hash_mismatch",
                "operator_unlock_hash_mismatch",
                "hard_cap_exceeded",
                "kill_switch_not_rechecked",
                "pre_order_risk_gate_not_rechecked",
            ],
        },
        "idempotency_and_reconciliation_requirement": {
            "idempotency_key_required": True,
            "reconciliation_required_after_any_testnet_session": True,
            "session_close_report_required": True,
            "reconciliation_mismatch_blocks_promotion": True,
        },
        "source_evidence_hash_summary": report.get("source_evidence_hash_summary"),
        "block_reasons": report.get("block_reasons"),
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": report.get("created_at_utc"),
    }


def _build_disabled_executor_guard_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "guard_type": "signed_testnet_disabled_executor_guard_review_only",
        "source_phase7_design_guard_id": report.get("phase7_signed_testnet_validation_design_guard_id"),
        "guard_passed": True,
        "guard_scope": "prove_executor_is_disabled_before_any_future_phase7_executor_stage",
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
        "future_executor_requirements": [
            "Separate explicit signed testnet executor approval packet.",
            "Fresh pre-submit validation generated after approval and operator unlock.",
            "Metadata-only key reference validation, no key value reads.",
            "Manual kill switch confirmation immediately before enablement review.",
            "Reconciliation and session close evidence for any future testnet session.",
        ],
        "created_at_utc": report.get("created_at_utc"),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return f"""# Phase 7 Signed Testnet Validation Design / Disabled Executor Guard — Review Only

Status: `{report.get('status')}`

This phase creates a signed-testnet validation design packet and disabled executor guard. It does not submit testnet orders, does not enable signed execution, and does not grant runtime authority.

## Result

- Phase 7 design ready review-only: `{report.get('phase7_design_ready_review_only')}`
- Phase 7 entry review possible from bridge: `{report.get('phase7_entry_review_possible_from_bridge')}`
- Signed testnet execution authority: `{report.get('phase7_execution_authority')}`
- Signed testnet order submission authority: `{report.get('phase7_order_submission_authority')}`
- Ready for signed testnet execution: `{report.get('ready_for_signed_testnet_execution')}`
- Testnet order submission allowed: `{report.get('testnet_order_submission_allowed')}`

## Blockers

{blocker_lines}

## Disabled Executor Guard

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`

## Next Step

Design review is allowed only as a review-only handoff. A separate future executor stage would be required before any signed testnet order submission can be considered.
"""


def build_phase7_signed_testnet_validation_design_guard_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    artifacts = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing_artifacts = [name for name, payload in artifacts.items() if not payload]
    unsafe_flags = _unsafe_flags_by_artifact(artifacts)
    phase6_6 = artifacts.get("phase6_6_actual_intake_validation_bridge", {})
    phase7_entry = artifacts.get("phase7_entry_review_packet", {})

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_SOURCE_ARTIFACT:{name}" for name in missing_artifacts])
    if unsafe_flags:
        blockers.extend([f"UNSAFE_PHASE7_SOURCE_FLAG:{name}:{','.join(flags)}" for name, flags in unsafe_flags.items()])

    bridge_ready = (
        phase6_6.get("status") == "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_RECORDED_REVIEW_ONLY"
        and phase6_6.get("phase7_entry_review_possible") is True
        and phase6_6.get("phase7_execution_authority") is False
        and phase6_6.get("phase7_order_submission_authority") is False
    )
    if not bridge_ready:
        blockers.append("PHASE6_6_BRIDGE_NOT_READY_FOR_PHASE7_DESIGN_REVIEW")

    entry_packet_ready = (
        phase7_entry.get("packet_type") == "phase7_entry_review_packet_review_only"
        and phase7_entry.get("phase7_entry_review_possible") is True
        and phase7_entry.get("phase7_execution_authority") is False
        and phase7_entry.get("phase7_order_submission_authority") is False
    )
    if not entry_packet_ready:
        blockers.append("PHASE7_ENTRY_REVIEW_PACKET_NOT_READY_OR_NOT_REVIEW_ONLY")

    for artifact_name, payload in artifacts.items():
        if payload.get("ready_for_signed_testnet_execution") is True:
            blockers.append(f"UNSAFE_READY_FOR_SIGNED_TESTNET_TRUE:{artifact_name}")
        if payload.get("testnet_order_submission_allowed") is True:
            blockers.append(f"UNSAFE_TESTNET_ORDER_SUBMISSION_ALLOWED_TRUE:{artifact_name}")
        if payload.get("external_order_submission_performed") is True:
            blockers.append(f"UNSAFE_EXTERNAL_ORDER_SUBMISSION_PERFORMED_TRUE:{artifact_name}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    design_ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if design_ready else STATUS_BLOCKED_REVIEW_ONLY
    phase7_id = stable_id(
        "phase7_signed_testnet_validation_design_guard",
        {
            "source_hashes": {name: _artifact_hash(payload) for name, payload in artifacts.items()},
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase7_signed_testnet_validation_design_guard_id": phase7_id,
        "phase7_version": PHASE7_VERSION,
        "status": status,
        "blocked": not design_ready,
        "fail_closed": not design_ready,
        "review_only": True,
        "design_only": True,
        "disabled_executor_guard": True,
        "phase7_design_ready_review_only": design_ready,
        "phase7_entry_review_possible_from_bridge": phase6_6.get("phase7_entry_review_possible") is True,
        "phase7_validation_design_packet_created": True,
        "disabled_executor_guard_report_created": True,
        "signed_testnet_validation_design_only": True,
        "missing_source_artifacts": missing_artifacts,
        "unsafe_flags_by_artifact": unsafe_flags,
        "source_evidence_hash_summary": {name: _source_summary(name, payload) for name, payload in artifacts.items()},
        "block_reasons": blockers,
        "order_lifecycle_design_scope": [
            "submit_design",
            "cancel_design",
            "fill_tracking_design",
            "position_sync_design",
            "balance_margin_leverage_check_design",
            "fee_slippage_min_notional_check_design",
            "reconciliation_design",
            "session_close_design",
        ],
        "future_phase7_executor_stage_required_before_any_order": True,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
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
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "recommended_next_action": "prepare_future_phase7_disabled_executor_stage_review" if design_ready else "resolve_phase7_design_blockers_and_rerun_phase6_6_phase7_design_guard",
        "created_at_utc": created,
    }
    report["signed_testnet_validation_design_packet_sha256"] = sha256_json(_build_validation_design_packet(report))
    report["disabled_executor_guard_report_sha256"] = sha256_json(_build_disabled_executor_guard_report(report))
    report["phase7_report_sha256"] = sha256_json(report)
    return report


def persist_phase7_signed_testnet_validation_design_guard_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_signed_testnet_validation_design_guard")
    report = build_phase7_signed_testnet_validation_design_guard_report(cfg=cfg)
    design_packet = _build_validation_design_packet(report)
    guard_report = _build_disabled_executor_guard_report(report)
    markdown = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_signed_testnet_validation_design_guard_report.json", report)
    atomic_write_json(latest / "signed_testnet_validation_design_packet_review_only.json", design_packet)
    atomic_write_json(latest / "signed_testnet_disabled_executor_guard_report.json", guard_report)
    (latest / "SIGNED_TESTNET_VALIDATION_DESIGN_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")

    atomic_write_json(phase_dir / "phase7_signed_testnet_validation_design_guard_report.json", report)
    atomic_write_json(phase_dir / "signed_testnet_validation_design_packet_review_only.json", design_packet)
    atomic_write_json(phase_dir / "signed_testnet_disabled_executor_guard_report.json", guard_report)
    (phase_dir / "SIGNED_TESTNET_VALIDATION_DESIGN_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_REGISTRY_NAME),
        {
            "phase7_signed_testnet_validation_design_guard_id": report.get("phase7_signed_testnet_validation_design_guard_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_design_ready_review_only": report.get("phase7_design_ready_review_only"),
            "phase7_execution_authority": False,
            "phase7_order_submission_authority": False,
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
        registry_name=PHASE7_REGISTRY_NAME,
        id_field="phase7_signed_testnet_validation_design_guard_registry_record_id",
        hash_field="phase7_signed_testnet_validation_design_guard_registry_record_sha256",
        id_prefix="phase7_signed_testnet_validation_design_guard_registry_record",
    )
    atomic_write_json(latest / "phase7_signed_testnet_validation_design_guard_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_signed_testnet_validation_design_guard_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_signed_testnet_validation_design_guard_report",
    "persist_phase7_signed_testnet_validation_design_guard_report",
]
