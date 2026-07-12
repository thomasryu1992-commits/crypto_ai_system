from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

PHASE5_VERSION = "phase5_manual_approval_intake_validation_v1"
PHASE5_REGISTRY_NAME = "phase5_manual_approval_intake_validation_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE5_MANUAL_APPROVAL_INTAKE_VALIDATION_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE5_MANUAL_APPROVAL_INTAKE_BLOCKED_REVIEW_ONLY"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
APPROVAL_INTAKE_VALIDATED_BY_THIS_MODULE = False
SIGNED_TESTNET_UNLOCK_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False


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


def _read_optional_submission(cfg: AppConfig) -> dict[str, Any]:
    candidates = [
        cfg.root / "storage" / "manual_approval" / "approval_intake_submission.json",
        _latest_dir(cfg) / "manual_approval_intake_submission.json",
    ]
    for path in candidates:
        payload = read_json(path, default={})
        if isinstance(payload, Mapping) and payload:
            return dict(payload)
    return {}


def _verify_embedded_hash(payload: Mapping[str, Any], field: str) -> bool:
    expected = payload.get(field)
    if not isinstance(expected, str) or not expected:
        return False
    body = dict(payload)
    body.pop(field, None)
    return sha256_json(body) == expected


def _source_report_hash_valid(phase4_3_report: Mapping[str, Any], expected: Any) -> bool:
    if not isinstance(expected, str) or not expected:
        return False
    actual = phase4_3_report.get("phase4_3_report_sha256")
    if actual == expected:
        return True
    if not isinstance(actual, str) or not actual:
        body = dict(phase4_3_report)
        body.pop("phase4_3_report_sha256", None)
        actual = sha256_json(body)
    return actual == expected


def _candidate_hash_valid(candidate: Mapping[str, Any]) -> bool:
    expected = candidate.get("profile_candidate_hash")
    if not isinstance(expected, str) or not expected:
        return False
    body = dict(candidate)
    body.pop("profile_candidate_hash", None)
    return sha256_json(body) == expected


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _manual_submission_blockers(submission: Mapping[str, Any]) -> list[str]:
    if not submission:
        return ["MANUAL_APPROVAL_SUBMISSION_MISSING"]
    required_fields = [
        "approval_packet_id",
        "approval_intake_id",
        "approver_info",
        "ticket_or_signature",
        "source_report_hash",
        "approval_packet_hash",
        "feature_matrix_hash",
        "profile_candidate_hash",
        "canonical_utc_timestamp",
    ]
    blockers: list[str] = []
    for field in required_fields:
        if not _safe_text(submission.get(field)):
            blockers.append(f"MANUAL_APPROVAL_FIELD_MISSING:{field}")
    timestamp = submission.get("canonical_utc_timestamp")
    if timestamp and not is_canonical_utc_timestamp(str(timestamp)):
        blockers.append("MANUAL_APPROVAL_TIMESTAMP_NOT_CANONICAL_UTC")
    unsafe_truthy_fields = [
        "signed_testnet_unlock_allowed",
        "testnet_order_submission_allowed",
        "live_trading_allowed",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "candidate_profile_applied",
        "external_order_submission_performed",
        "auto_promotion_allowed",
    ]
    for field in unsafe_truthy_fields:
        if bool(submission.get(field)):
            blockers.append(f"UNSAFE_MANUAL_APPROVAL_FIELD_TRUE:{field}")
    return blockers


def _artifact_blockers(
    *,
    phase4_4: Mapping[str, Any],
    review_packet: Mapping[str, Any],
    approval_draft: Mapping[str, Any],
    phase4_3: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if phase4_4.get("status") != "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE4_4_REVIEW_PACKET_NOT_READY")
    if not review_packet:
        blockers.append("CANDIDATE_PROFILE_REVIEW_PACKET_MISSING")
    elif not _verify_embedded_hash(review_packet, "candidate_profile_review_packet_sha256"):
        blockers.append("CANDIDATE_PROFILE_REVIEW_PACKET_HASH_INVALID")
    if not approval_draft:
        blockers.append("APPROVAL_PACKET_DRAFT_MISSING")
    else:
        if approval_draft.get("status") != "APPROVAL_PACKET_DRAFT_REVIEW_ONLY_NOT_APPROVED":
            blockers.append("APPROVAL_PACKET_DRAFT_STATUS_INVALID")
        if approval_draft.get("validation_status") != "NOT_SUBMITTED_REVIEW_ONLY":
            blockers.append("APPROVAL_PACKET_DRAFT_VALIDATION_STATUS_INVALID")
        if not _verify_embedded_hash(approval_draft, "approval_packet_draft_sha256"):
            blockers.append("APPROVAL_PACKET_DRAFT_HASH_INVALID")
        if approval_draft.get("approval_packet_id") is not None:
            blockers.append("APPROVAL_PACKET_DRAFT_HAS_APPROVAL_PACKET_ID")
        if approval_draft.get("approval_intake_id") is not None:
            blockers.append("APPROVAL_PACKET_DRAFT_HAS_APPROVAL_INTAKE_ID")
        if approval_draft.get("approval_packet_created") is not False:
            blockers.append("APPROVAL_PACKET_DRAFT_CREATED_FLAG_NOT_FALSE")
    if approval_draft and review_packet:
        if approval_draft.get("candidate_profile_review_packet_sha256") != review_packet.get("candidate_profile_review_packet_sha256"):
            blockers.append("REVIEW_PACKET_HASH_CHAIN_MISMATCH")
        if approval_draft.get("profile_candidate_hash") != review_packet.get("profile_candidate_hash"):
            blockers.append("PROFILE_CANDIDATE_HASH_CHAIN_MISMATCH")
        if approval_draft.get("feature_matrix_sha256") != review_packet.get("feature_matrix_sha256"):
            blockers.append("FEATURE_MATRIX_HASH_CHAIN_MISMATCH")
    if approval_draft and phase4_3:
        if not _source_report_hash_valid(phase4_3, approval_draft.get("source_report_hash")):
            blockers.append("SOURCE_REPORT_HASH_MISMATCH")
    if candidate and not _candidate_hash_valid(candidate):
        blockers.append("CANDIDATE_PROFILE_HASH_INVALID")
    unsafe_fields = [
        "signed_testnet_unlock_allowed",
        "testnet_order_submission_allowed",
        "live_trading_allowed_by_this_module",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "candidate_profile_applied",
        "external_order_submission_performed",
        "auto_promotion_allowed",
    ]
    for source_name, payload in {
        "phase4_4": phase4_4,
        "review_packet": review_packet,
        "approval_draft": approval_draft,
    }.items():
        for field in unsafe_fields:
            if bool(payload.get(field)):
                blockers.append(f"UNSAFE_FLAG_TRUE:{source_name}:{field}")
    return blockers


def build_phase5_manual_approval_intake_validation_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    phase4_4 = _read_latest_json(cfg, "phase4_4_candidate_profile_review_packet_report.json")
    review_packet = _read_latest_json(cfg, "candidate_profile_review_packet.json")
    approval_draft = _read_latest_json(cfg, "approval_packet_draft_review_only.json")
    phase4_3 = _read_latest_json(cfg, "phase4_3_research_signal_score_bucket_replay_report.json")
    candidate = _read_latest_json(cfg, "drift_reduced_candidate_profile_draft.json")
    submission = _read_optional_submission(cfg)

    blockers = _artifact_blockers(
        phase4_4=phase4_4,
        review_packet=review_packet,
        approval_draft=approval_draft,
        phase4_3=phase4_3,
        candidate=candidate,
    )
    blockers.extend(_manual_submission_blockers(submission))
    blockers = sorted(dict.fromkeys(blockers))
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    created = utc_now_canonical()

    validation_seed = {
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "candidate_profile_review_packet_id": review_packet.get("candidate_profile_review_packet_id"),
        "manual_submission_present": bool(submission),
        "blocked": blocked,
        "created_at_utc": created,
    }
    validation_id = stable_id("phase5_manual_approval_intake_validation", validation_seed, 24)
    intake_record_id = stable_id("manual_approval_intake_validation_record", validation_seed, 24)

    submission_matches = False
    if submission and approval_draft:
        submission_matches = (
            submission.get("source_report_hash") == approval_draft.get("source_report_hash")
            and submission.get("feature_matrix_hash") == approval_draft.get("feature_matrix_sha256")
            and submission.get("profile_candidate_hash") == approval_draft.get("profile_candidate_hash")
        )
        if not submission_matches:
            blockers.append("MANUAL_APPROVAL_SUBMISSION_HASH_CHAIN_MISMATCH")
            blockers = sorted(dict.fromkeys(blockers))
            blocked = True
            status = STATUS_BLOCKED_REVIEW_ONLY

    payload: dict[str, Any] = {
        "phase5_manual_approval_intake_validation_id": validation_id,
        "phase5_version": PHASE5_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "manual_approval_submission_present": bool(submission),
        "manual_approval_submission_hash_chain_matches_draft": submission_matches,
        "approval_intake_validation_record_created": True,
        "approval_intake_validation_record_id": intake_record_id,
        "approval_intake_submitted": bool(submission),
        "approval_intake_validated": False,
        "approval_intake_status": "BLOCKED_FAIL_CLOSED" if blocked else "VALIDATED_REVIEW_ONLY_NOT_RUNTIME_AUTHORITY",
        "approval_packet_created": False,
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "approval_packet_draft_sha256": approval_draft.get("approval_packet_draft_sha256"),
        "approval_packet_draft_hash_valid": _verify_embedded_hash(approval_draft, "approval_packet_draft_sha256") if approval_draft else False,
        "candidate_profile_review_packet_id": review_packet.get("candidate_profile_review_packet_id"),
        "candidate_profile_review_packet_sha256": review_packet.get("candidate_profile_review_packet_sha256"),
        "candidate_profile_review_packet_hash_valid": _verify_embedded_hash(review_packet, "candidate_profile_review_packet_sha256") if review_packet else False,
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash") or approval_draft.get("profile_candidate_hash"),
        "candidate_profile_hash_valid": _candidate_hash_valid(candidate) if candidate else False,
        "source_report_path": approval_draft.get("source_report_path"),
        "source_report_hash": approval_draft.get("source_report_hash"),
        "source_report_hash_valid": _source_report_hash_valid(phase4_3, approval_draft.get("source_report_hash")) if phase4_3 and approval_draft else False,
        "feature_matrix_sha256": approval_draft.get("feature_matrix_sha256"),
        "source_bundle_sha256": approval_draft.get("source_bundle_sha256"),
        "data_snapshot_id": approval_draft.get("data_snapshot_id"),
        "feature_snapshot_id": approval_draft.get("feature_snapshot_id"),
        "manual_submission_required_fields": [
            "approval_packet_id",
            "approval_intake_id",
            "approver_info",
            "ticket_or_signature",
            "source_report_hash",
            "approval_packet_hash",
            "feature_matrix_hash",
            "profile_candidate_hash",
            "canonical_utc_timestamp",
        ],
        "block_reasons": blockers,
        "recommended_next_action": "provide_manual_approval_submission_for_review" if blocked else "manual_approval_review_recorded_no_runtime_unlock",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_execution_unlock_authority": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    payload["phase5_report_sha256"] = sha256_json(payload)
    return payload


def _build_intake_validation_record(report: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "approval_intake_validation_record_id": report.get("approval_intake_validation_record_id"),
        "phase5_manual_approval_intake_validation_id": report.get("phase5_manual_approval_intake_validation_id"),
        "status": report.get("approval_intake_status"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "review_only": True,
        "approval_intake_submitted": report.get("approval_intake_submitted"),
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "approval_packet_draft_id": report.get("approval_packet_draft_id"),
        "candidate_profile_review_packet_id": report.get("candidate_profile_review_packet_id"),
        "candidate_profile_id": report.get("candidate_profile_id"),
        "profile_candidate_hash": report.get("profile_candidate_hash"),
        "source_report_hash": report.get("source_report_hash"),
        "feature_matrix_sha256": report.get("feature_matrix_sha256"),
        "block_reasons": report.get("block_reasons", []),
        "runtime_permission_source": False,
        "signed_testnet_unlock_allowed": False,
        "testnet_order_submission_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "created_at_utc": report.get("created_at_utc") or utc_now_canonical(),
    }
    record["approval_intake_validation_record_sha256"] = sha256_json(record)
    return record


def persist_phase5_manual_approval_intake_validation_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase5_manual_approval_intake_validation")
    report = build_phase5_manual_approval_intake_validation_report(cfg=cfg)
    intake_record = _build_intake_validation_record(report)

    atomic_write_json(latest / "phase5_manual_approval_intake_validation_report.json", report)
    atomic_write_json(phase_dir / "phase5_manual_approval_intake_validation_report.json", report)
    atomic_write_json(latest / "approval_intake_validation_record_review_only.json", intake_record)
    atomic_write_json(phase_dir / "approval_intake_validation_record_review_only.json", intake_record)

    registry_record = append_registry_record(
        registry_path(cfg, PHASE5_REGISTRY_NAME),
        {
            "phase5_manual_approval_intake_validation_id": report.get("phase5_manual_approval_intake_validation_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "manual_approval_submission_present": report.get("manual_approval_submission_present"),
            "approval_intake_status": report.get("approval_intake_status"),
            "approval_intake_validated": False,
            "approval_packet_created": False,
            "candidate_profile_id": report.get("candidate_profile_id"),
            "profile_candidate_hash": report.get("profile_candidate_hash"),
            "block_reasons": report.get("block_reasons", []),
            "signed_testnet_unlock_allowed": False,
            "testnet_order_submission_allowed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "candidate_profile_applied": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE5_REGISTRY_NAME,
        id_field="phase5_manual_approval_intake_validation_registry_record_id",
        hash_field="phase5_manual_approval_intake_validation_registry_record_sha256",
        id_prefix="phase5_manual_approval_intake_validation_registry_record",
    )
    atomic_write_json(latest / "phase5_manual_approval_intake_validation_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase5_manual_approval_intake_validation_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE5_VERSION",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "STATUS_RECORDED_REVIEW_ONLY",
    "build_phase5_manual_approval_intake_validation_report",
    "persist_phase5_manual_approval_intake_validation_report",
]
