from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE6_4_VERSION = "phase6_4_signed_testnet_readiness_review_packet_v1"
PHASE6_4_REGISTRY_NAME = "phase6_4_signed_testnet_readiness_review_packet_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE6_4_SIGNED_TESTNET_READINESS_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE6_4_SIGNED_TESTNET_READINESS_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"

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
    "phase5_manual_approval_intake_validation": "phase5_manual_approval_intake_validation_report.json",
    "phase5_1_manual_approval_operator_handoff": "phase5_1_manual_approval_operator_handoff_report.json",
    "phase5_2_manual_approval_submission_fixture_validator": "phase5_2_manual_approval_submission_fixture_validator_report.json",
    "phase6_signed_testnet_preparation_preview": "phase6_signed_testnet_preparation_preview_report.json",
    "phase6_1_operator_unlock_request_template": "phase6_1_signed_testnet_operator_unlock_request_template_report.json",
    "phase6_2_operator_unlock_request_fixture_validator": "phase6_2_operator_unlock_request_fixture_validator_report.json",
    "phase6_3_signed_testnet_readiness_gate_review": "phase6_3_signed_testnet_readiness_gate_review_report.json",
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


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase5_report_sha256",
        "phase5_1_report_sha256",
        "phase5_2_report_sha256",
        "phase6_report_sha256",
        "phase6_1_report_sha256",
        "phase6_2_report_sha256",
        "phase6_3_report_sha256",
        "phase6_4_report_sha256",
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
        "status": data.get("status"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _unsafe_flags_by_artifact(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    unsafe: dict[str, list[str]] = {}
    for name, payload in artifacts.items():
        flags = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(dict(payload or {}).get(field))]
        if flags:
            unsafe[name] = flags
    return unsafe


def _build_operator_checklist(blockers: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "check_id": "manual_approval_submission",
            "description": "Create and validate storage/manual_approval/approval_intake_submission.json only after human approval.",
            "required_before_signed_testnet": True,
            "current_status": "missing" if "ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING" in blockers else "review_required",
        },
        {
            "check_id": "approval_intake_validation",
            "description": "Rerun Phase 5 and require approval_intake_validated=true with matching hash-chain evidence.",
            "required_before_signed_testnet": True,
            "current_status": "not_validated" if "APPROVAL_INTAKE_NOT_VALIDATED" in blockers else "review_required",
        },
        {
            "check_id": "operator_unlock_request",
            "description": "Create and validate storage/latest/operator_unlock_request.json only after approval intake passes.",
            "required_before_signed_testnet": True,
            "current_status": "missing" if "ACTUAL_OPERATOR_UNLOCK_REQUEST_MISSING" in blockers else "review_required",
        },
        {
            "check_id": "hard_caps_and_kill_switch",
            "description": "Operator must recheck max notional, max order count, daily loss cap, kill switch, and PreOrderRiskGate before any later signed testnet session.",
            "required_before_signed_testnet": True,
            "current_status": "manual_required",
        },
        {
            "check_id": "executor_flags",
            "description": "Confirm ready_for_signed_testnet_execution, testnet_order_submission_allowed, place_order_enabled, cancel_order_enabled, and signed_order_executor_enabled remain false in this package.",
            "required_before_signed_testnet": True,
            "current_status": "disabled_in_review_packet",
        },
        {
            "check_id": "secret_policy",
            "description": "Confirm no API key values, API secret values, or secret files were read or created; only metadata-only references are allowed.",
            "required_before_signed_testnet": True,
            "current_status": "metadata_only_required",
        },
    ]


def _build_handoff_markdown(packet: Mapping[str, Any]) -> str:
    blockers = packet.get("readiness_blockers") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    checklist = packet.get("operator_decision_checklist") or []
    checklist_lines = "\n".join(
        f"- `{item.get('check_id')}` — {item.get('description')} Current: `{item.get('current_status')}`"
        for item in checklist
    )
    hashes = packet.get("source_evidence_hash_summary") or {}
    hash_lines = "\n".join(f"- `{name}`: `{value.get('sha256')}`" for name, value in hashes.items())
    return f"""# Phase 6.4 Signed Testnet Readiness Review Packet / Operator Decision Handoff — Review Only

Status: `{packet.get('status')}`

This packet consolidates Phase 5 through Phase 6.3 signed-testnet readiness evidence for a human operator decision. It does not create a manual approval submission, does not create an operator unlock request, does not enable the signed executor, and does not submit testnet or live orders.

## Current Readiness Result

- Signed testnet readiness: `{packet.get('signed_testnet_readiness_status')}`
- Ready for signed testnet execution: `{packet.get('ready_for_signed_testnet_execution')}`
- Testnet order submission allowed: `{packet.get('testnet_order_submission_allowed')}`
- Signed order executor enabled: `{packet.get('signed_order_executor_enabled')}`

## Readiness Blockers

{blocker_lines}

## Source Evidence Hash Summary

{hash_lines}

## Operator Decision Checklist

{checklist_lines}

## Required Manual Artifacts Before Any Future Recheck

- `storage/manual_approval/approval_intake_submission.json`
- `storage/latest/operator_unlock_request.json`

## Safety Invariants

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`
- `runtime_settings_mutated=false`
- `score_weights_mutated=false`
- `auto_promotion_allowed=false`

## Next Step

A human operator must create the missing manual approval and operator unlock artifacts outside this review-only generator, then rerun Phase 5, Phase 6, Phase 6.3, and Phase 6.4. Any missing hash, missing signature, unsafe flag, or hard-cap mismatch must keep signed testnet readiness blocked.
"""


def build_phase6_4_signed_testnet_readiness_review_packet_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    created = utc_now_canonical()
    artifacts = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_ARTIFACTS.items()}
    phase6_3 = artifacts["phase6_3_signed_testnet_readiness_gate_review"]
    missing_artifacts = [name for name, payload in artifacts.items() if not payload]
    unsafe_flags = _unsafe_flags_by_artifact(artifacts)

    readiness_blockers = list(phase6_3.get("readiness_blockers") or [])
    readiness_blockers.extend([f"MISSING_REVIEW_PACKET_SOURCE_ARTIFACT:{name}" for name in missing_artifacts])
    if unsafe_flags:
        readiness_blockers.extend([f"UNSAFE_REVIEW_PACKET_SOURCE_FLAG:{name}:{','.join(flags)}" for name, flags in unsafe_flags.items()])
    readiness_blockers = sorted(dict.fromkeys(readiness_blockers))

    actual_approval_path = cfg.root / "storage" / "manual_approval" / "approval_intake_submission.json"
    actual_unlock_latest_path = latest / "operator_unlock_request.json"
    actual_unlock_archive_path = cfg.root / "storage" / "signed_testnet" / "operator_unlock_request.json"
    actual_approval_present = actual_approval_path.exists()
    actual_unlock_present = actual_unlock_latest_path.exists() or actual_unlock_archive_path.exists()

    packet_id = stable_id(
        "phase6_4_signed_testnet_readiness_review_packet",
        {
            "phase6_3_hash": _artifact_hash(phase6_3),
            "source_hashes": {name: _artifact_hash(payload) for name, payload in artifacts.items()},
            "blockers": readiness_blockers,
            "created_at_utc": created,
        },
        24,
    )
    source_summaries = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    operator_checklist = _build_operator_checklist(readiness_blockers)
    readiness_status = "SIGNED_TESTNET_READINESS_BLOCKED_REVIEW_ONLY"

    review_packet: dict[str, Any] = {
        "phase6_4_signed_testnet_readiness_review_packet_id": packet_id,
        "phase6_4_version": PHASE6_4_VERSION,
        "status": STATUS_RECORDED_REVIEW_ONLY,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "operator_decision_handoff_created": True,
        "signed_testnet_readiness_status": readiness_status,
        "signed_testnet_readiness_passed": False,
        "actual_manual_approval_submission_present": actual_approval_present,
        "actual_operator_unlock_request_present": actual_unlock_present,
        "approval_intake_validated": False,
        "operator_unlock_request_validated": False,
        "readiness_blockers": readiness_blockers,
        "missing_review_packet_source_artifacts": missing_artifacts,
        "unsafe_flags_by_artifact": unsafe_flags,
        "source_evidence_hash_summary": source_summaries,
        "operator_decision_checklist": operator_checklist,
        "required_manual_artifacts_before_recheck": [
            "storage/manual_approval/approval_intake_submission.json",
            "storage/latest/operator_unlock_request.json",
        ],
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
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "recommended_next_action": "operator_reviews_handoff_then_manually_creates_required_artifacts_if_approved_and_reruns_phase5_phase6_phase6_3_phase6_4",
        "created_at_utc": created,
    }
    review_packet["phase6_4_review_packet_sha256"] = sha256_json(review_packet)
    return review_packet


def persist_phase6_4_signed_testnet_readiness_review_packet_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase6_4_signed_testnet_readiness_review_packet")
    report = build_phase6_4_signed_testnet_readiness_review_packet_report(cfg=cfg)
    markdown = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase6_4_signed_testnet_readiness_review_packet_report.json", report)
    atomic_write_json(latest / "signed_testnet_readiness_review_packet.json", report)
    (latest / "SIGNED_TESTNET_OPERATOR_DECISION_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")
    atomic_write_json(phase_dir / "phase6_4_signed_testnet_readiness_review_packet_report.json", report)
    atomic_write_json(phase_dir / "signed_testnet_readiness_review_packet.json", report)
    (phase_dir / "SIGNED_TESTNET_OPERATOR_DECISION_HANDOFF_REVIEW_ONLY.md").write_text(markdown, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE6_4_REGISTRY_NAME),
        {
            "phase6_4_signed_testnet_readiness_review_packet_id": report.get("phase6_4_signed_testnet_readiness_review_packet_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "signed_testnet_readiness_passed": False,
            "actual_manual_approval_submission_present": report.get("actual_manual_approval_submission_present"),
            "actual_operator_unlock_request_present": report.get("actual_operator_unlock_request_present"),
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
        registry_name=PHASE6_4_REGISTRY_NAME,
        id_field="phase6_4_signed_testnet_readiness_review_packet_registry_record_id",
        hash_field="phase6_4_signed_testnet_readiness_review_packet_registry_record_sha256",
        id_prefix="phase6_4_signed_testnet_readiness_review_packet_registry_record",
    )
    atomic_write_json(latest / "phase6_4_signed_testnet_readiness_review_packet_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase6_4_signed_testnet_readiness_review_packet_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE6_4_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase6_4_signed_testnet_readiness_review_packet_report",
    "persist_phase6_4_signed_testnet_readiness_review_packet_report",
]
