from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.common import (
    bool_value as _bool,
    hash_latest as _hash_latest,
    latest_dir as _latest_dir,
    read_latest_json as _read_latest_json,
    text_value as _safe_text,
    storage_dir as _storage_dir,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

PHASE4_4_VERSION = "phase4_4_candidate_profile_review_packet_v1"
PHASE4_4_REGISTRY_NAME = "phase4_4_candidate_profile_review_packet_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
APPROVAL_PACKET_DRAFT_ONLY_BY_THIS_MODULE = True
APPROVAL_INTAKE_SUBMITTED_BY_THIS_MODULE = False
SETTINGS_WRITE_PREVIEW_APPLIED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
SIGNED_TESTNET_UNLOCK_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False


def _candidate_hash_valid(candidate: Mapping[str, Any]) -> bool:
    expected = candidate.get("profile_candidate_hash")
    if not isinstance(expected, str) or not expected:
        return False
    body = dict(candidate)
    body.pop("profile_candidate_hash", None)
    return sha256_json(body) == expected


def _source_artifacts(cfg: AppConfig) -> dict[str, dict[str, Any]]:
    latest = _latest_dir(cfg)
    names = [
        "drift_reduced_candidate_profile_draft.json",
        "phase4_3_research_signal_score_bucket_replay_report.json",
        "paper_outcome_score_bucket_enriched_outcomes.json",
        "feature_store_manifest.json",
        "data_snapshot_manifest.json",
        "paper_data_quality_gate_report.json",
        "paper_strategy_validation_report.json",
    ]
    return {
        name: {
            "path": str(latest / name),
            "exists": (latest / name).exists(),
            "sha256": _hash_latest(cfg, name),
        }
        for name in names
    }


def _build_candidate_review_packet(
    *,
    candidate: Mapping[str, Any],
    phase4_3: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    data_snapshot_manifest: Mapping[str, Any],
    created_at_utc: str,
) -> dict[str, Any]:
    seed = {
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "phase4_3_report_id": phase4_3.get("phase4_3_research_signal_score_bucket_replay_id"),
        "created_at_utc": created_at_utc,
    }
    packet_id = stable_id("candidate_profile_review_packet", seed, 24)
    packet: dict[str, Any] = {
        "candidate_profile_review_packet_id": packet_id,
        "packet_version": PHASE4_4_VERSION,
        "status": "CANDIDATE_PROFILE_REVIEW_PACKET_DRAFT_REVIEW_ONLY",
        "review_only": True,
        "paper_only": True,
        "manual_approval_required": True,
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "candidate_profile_status": candidate.get("status"),
        "profile_version": candidate.get("profile_version"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "profile_candidate_hash_valid": _candidate_hash_valid(candidate),
        "source_report_id": candidate.get("source_report_id"),
        "source_report_hash": phase4_3.get("phase4_3_report_sha256"),
        "source_report_path": "storage/latest/phase4_3_research_signal_score_bucket_replay_report.json",
        "source_dimension": candidate.get("source_dimension"),
        "source_value": candidate.get("source_value"),
        "feature_matrix_sha256": candidate.get("feature_matrix_sha256") or feature_manifest.get("feature_matrix_sha256"),
        "source_bundle_sha256": candidate.get("source_bundle_sha256") or feature_manifest.get("source_bundle_sha256"),
        "data_snapshot_id": data_snapshot_manifest.get("data_snapshot_id") or feature_manifest.get("data_snapshot_id"),
        "feature_snapshot_id": feature_manifest.get("feature_snapshot_id"),
        "data_snapshot_manifest_sha256": _safe_text(data_snapshot_manifest.get("data_snapshot_manifest_sha256")),
        "feature_store_manifest_sha256": _safe_text(feature_manifest.get("feature_store_manifest_sha256")),
        "sample_size": candidate.get("sample_size"),
        "expectancy": candidate.get("expectancy"),
        "average_R": candidate.get("average_R"),
        "max_drawdown": candidate.get("max_drawdown"),
        "alignment_drift_rate": candidate.get("alignment_drift_rate"),
        "live_candidate_eligible": False,
        "signed_testnet_candidate_eligible": False,
        "manual_approval_packet_required_before_signed_testnet": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "approval_packet_draft_created": True,
        "approval_intake_submitted": False,
        "signed_testnet_unlock_allowed": False,
        "testnet_order_submission_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }
    packet["candidate_profile_review_packet_sha256"] = sha256_json(packet)
    return packet


def _build_approval_packet_draft(
    *,
    review_packet: Mapping[str, Any] | None,
    candidate: Mapping[str, Any],
    created_at_utc: str,
) -> dict[str, Any] | None:
    if not review_packet:
        return None
    seed = {
        "candidate_profile_review_packet_id": review_packet.get("candidate_profile_review_packet_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "created_at_utc": created_at_utc,
    }
    draft_id = stable_id("approval_packet_draft", seed, 24)
    draft: dict[str, Any] = {
        "approval_packet_draft_id": draft_id,
        "approval_packet_id": None,
        "approval_intake_id": None,
        "status": "APPROVAL_PACKET_DRAFT_REVIEW_ONLY_NOT_APPROVED",
        "validation_status": "NOT_SUBMITTED_REVIEW_ONLY",
        "review_only": True,
        "paper_only": True,
        "manual_approval_required": True,
        "approver_info_required": True,
        "ticket_or_signature_required": True,
        "approval_intake_submitted": False,
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "approval_packet_draft_created": True,
        "candidate_profile_review_packet_id": review_packet.get("candidate_profile_review_packet_id"),
        "candidate_profile_review_packet_sha256": review_packet.get("candidate_profile_review_packet_sha256"),
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "source_report_path": review_packet.get("source_report_path"),
        "source_report_hash": review_packet.get("source_report_hash"),
        "feature_matrix_sha256": review_packet.get("feature_matrix_sha256"),
        "source_bundle_sha256": review_packet.get("source_bundle_sha256"),
        "data_snapshot_id": review_packet.get("data_snapshot_id"),
        "feature_snapshot_id": review_packet.get("feature_snapshot_id"),
        "signed_testnet_unlock_allowed": False,
        "testnet_order_submission_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }
    draft["approval_packet_draft_sha256"] = sha256_json(draft)
    return draft


def _build_disabled_settings_preview(review_packet: Mapping[str, Any] | None, candidate: Mapping[str, Any]) -> str:
    candidate_id = candidate.get("candidate_profile_id") or "missing_candidate_profile"
    packet_id = review_packet.get("candidate_profile_review_packet_id") if review_packet else "missing_review_packet"
    return "\n".join(
        [
            "# DISABLED SETTINGS WRITE PREVIEW — REVIEW ONLY",
            f"# candidate_profile_id={candidate_id}",
            f"# candidate_profile_review_packet_id={packet_id}",
            "# No settings.yaml mutation is performed.",
            "# No runtime score_weights mutation is performed.",
            "# No place_order/cancel_order/signed_order_executor enablement is performed.",
            "# Manual approval intake is required before any runtime-impacting stage.",
            "",
            "# Example only, not applied:",
            "# candidate_profiles:",
            f"#   - id: {candidate_id}",
            "#     status: review_only_draft_not_applied",
            "",
        ]
    )


def _blockers(
    *,
    candidate: Mapping[str, Any],
    phase4_3: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    data_snapshot_manifest: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    for name, meta in artifacts.items():
        if name in {"drift_reduced_candidate_profile_draft.json", "phase4_3_research_signal_score_bucket_replay_report.json", "feature_store_manifest.json", "data_snapshot_manifest.json"} and not meta.get("exists"):
            blockers.append(f"MISSING_REQUIRED_ARTIFACT:{name}")
    if not candidate:
        blockers.append("CANDIDATE_PROFILE_DRAFT_MISSING")
    if candidate and candidate.get("status") != "review_only_draft":
        blockers.append("CANDIDATE_PROFILE_DRAFT_NOT_REVIEW_ONLY_DRAFT")
    if candidate and not _candidate_hash_valid(candidate):
        blockers.append("PROFILE_CANDIDATE_HASH_INVALID")
    if phase4_3.get("status") != "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE4_3_SCORE_BUCKET_REPLAY_NOT_READY")
    if not phase4_3.get("candidate_profile_draft_created"):
        blockers.append("PHASE4_3_CANDIDATE_DRAFT_NOT_CREATED")
    if not candidate.get("feature_matrix_sha256") and not feature_manifest.get("feature_matrix_sha256"):
        blockers.append("FEATURE_MATRIX_SHA256_MISSING")
    if not candidate.get("source_bundle_sha256") and not feature_manifest.get("source_bundle_sha256"):
        blockers.append("SOURCE_BUNDLE_SHA256_MISSING")
    if not (data_snapshot_manifest.get("data_snapshot_id") or feature_manifest.get("data_snapshot_id")):
        blockers.append("DATA_SNAPSHOT_ID_MISSING")
    if not feature_manifest.get("feature_snapshot_id"):
        blockers.append("FEATURE_SNAPSHOT_ID_MISSING")
    unsafe_flags = [
        "runtime_settings_mutated",
        "score_weights_mutated",
        "candidate_profile_applied",
        "approval_packet_created",
        "auto_promotion_allowed",
        "live_candidate_eligible",
        "live_trading_allowed_by_this_module",
        "external_order_submission_performed",
        "signed_testnet_unlock_allowed",
        "testnet_order_submission_allowed",
    ]
    for flag in unsafe_flags:
        if _bool(candidate.get(flag)) or _bool(phase4_3.get(flag)):
            blockers.append(f"UNSAFE_FLAG_TRUE:{flag}")
    return sorted(dict.fromkeys(blockers))


def build_phase4_4_candidate_profile_review_packet_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    candidate = _read_latest_json(cfg, "drift_reduced_candidate_profile_draft.json")
    phase4_3 = _read_latest_json(cfg, "phase4_3_research_signal_score_bucket_replay_report.json")
    feature_manifest = _read_latest_json(cfg, "feature_store_manifest.json")
    data_snapshot_manifest = _read_latest_json(cfg, "data_snapshot_manifest.json")
    artifacts = _source_artifacts(cfg)
    blockers = _blockers(
        candidate=candidate,
        phase4_3=phase4_3,
        feature_manifest=feature_manifest,
        data_snapshot_manifest=data_snapshot_manifest,
        artifacts=artifacts,
    )
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    created = utc_now_canonical()
    review_packet = None if blocked else _build_candidate_review_packet(
        candidate=candidate,
        phase4_3=phase4_3,
        feature_manifest=feature_manifest,
        data_snapshot_manifest=data_snapshot_manifest,
        created_at_utc=created,
    )
    approval_draft = _build_approval_packet_draft(review_packet=review_packet, candidate=candidate, created_at_utc=created) if review_packet else None
    report_seed = {
        "status": status,
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "phase4_3_report_id": phase4_3.get("phase4_3_research_signal_score_bucket_replay_id"),
        "blocked": blocked,
        "created_at_utc": created,
    }
    report_id = stable_id("phase4_4_candidate_profile_review_packet", report_seed, 24)
    payload: dict[str, Any] = {
        "phase4_4_candidate_profile_review_packet_id": report_id,
        "phase4_4_version": PHASE4_4_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "candidate_profile_hash": candidate.get("profile_candidate_hash"),
        "candidate_profile_hash_valid": _candidate_hash_valid(candidate) if candidate else False,
        "phase4_3_status": phase4_3.get("status"),
        "phase4_3_report_id": phase4_3.get("phase4_3_research_signal_score_bucket_replay_id"),
        "phase4_3_report_sha256": phase4_3.get("phase4_3_report_sha256"),
        "candidate_review_packet_created": bool(review_packet),
        "candidate_profile_review_packet_id": review_packet.get("candidate_profile_review_packet_id") if review_packet else None,
        "candidate_profile_review_packet_sha256": review_packet.get("candidate_profile_review_packet_sha256") if review_packet else None,
        "approval_packet_draft_created": bool(approval_draft),
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id") if approval_draft else None,
        "approval_packet_draft_sha256": approval_draft.get("approval_packet_draft_sha256") if approval_draft else None,
        "approval_packet_created": False,
        "approval_intake_submitted": False,
        "approval_intake_status": "NOT_SUBMITTED_REVIEW_ONLY",
        "manual_approval_readiness_status": "MANUAL_APPROVAL_REVIEW_PACKET_READY_REVIEW_ONLY" if review_packet else "MANUAL_APPROVAL_REVIEW_PACKET_BLOCKED_REVIEW_ONLY",
        "source_report_path": "storage/latest/phase4_3_research_signal_score_bucket_replay_report.json",
        "source_report_hash": phase4_3.get("phase4_3_report_sha256"),
        "feature_matrix_sha256": candidate.get("feature_matrix_sha256") or feature_manifest.get("feature_matrix_sha256"),
        "source_bundle_sha256": candidate.get("source_bundle_sha256") or feature_manifest.get("source_bundle_sha256"),
        "data_snapshot_id": data_snapshot_manifest.get("data_snapshot_id") or feature_manifest.get("data_snapshot_id"),
        "feature_snapshot_id": feature_manifest.get("feature_snapshot_id"),
        "source_artifacts": artifacts,
        "block_reasons": blockers,
        "recommended_next_action": "manual_review_only_approval_packet_intake" if review_packet else "fix_candidate_review_packet_blockers",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "signed_testnet_unlock_allowed": False,
        "testnet_order_submission_allowed": False,
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
    payload["phase4_4_report_sha256"] = sha256_json(payload)
    return payload


def persist_phase4_4_candidate_profile_review_packet_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase4_4_candidate_profile_review_packet")
    report = build_phase4_4_candidate_profile_review_packet_report(cfg=cfg)

    candidate = _read_latest_json(cfg, "drift_reduced_candidate_profile_draft.json")
    phase4_3 = _read_latest_json(cfg, "phase4_3_research_signal_score_bucket_replay_report.json")
    feature_manifest = _read_latest_json(cfg, "feature_store_manifest.json")
    data_snapshot_manifest = _read_latest_json(cfg, "data_snapshot_manifest.json")
    created = report.get("created_at_utc") or utc_now_canonical()

    review_packet = None
    approval_draft = None
    if report.get("candidate_review_packet_created"):
        review_packet = _build_candidate_review_packet(
            candidate=candidate,
            phase4_3=phase4_3,
            feature_manifest=feature_manifest,
            data_snapshot_manifest=data_snapshot_manifest,
            created_at_utc=str(created),
        )
        approval_draft = _build_approval_packet_draft(review_packet=review_packet, candidate=candidate, created_at_utc=str(created))
        atomic_write_json(latest / "candidate_profile_review_packet.json", review_packet)
        atomic_write_json(phase_dir / "candidate_profile_review_packet.json", review_packet)
        if approval_draft:
            atomic_write_json(latest / "approval_packet_draft_review_only.json", approval_draft)
            atomic_write_json(phase_dir / "approval_packet_draft_review_only.json", approval_draft)
        preview_text = _build_disabled_settings_preview(review_packet, candidate)
        (latest / "disabled_candidate_settings_write_preview.diff").write_text(preview_text, encoding="utf-8")
        (phase_dir / "disabled_candidate_settings_write_preview.diff").write_text(preview_text, encoding="utf-8")

    atomic_write_json(latest / "phase4_4_candidate_profile_review_packet_report.json", report)
    atomic_write_json(phase_dir / "phase4_4_candidate_profile_review_packet_report.json", report)

    registry_record = {
        "phase4_4_registry_version": PHASE4_4_VERSION,
        "phase4_4_candidate_profile_review_packet_id": report.get("phase4_4_candidate_profile_review_packet_id"),
        "phase4_4_report_sha256": report.get("phase4_4_report_sha256"),
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "candidate_profile_id": report.get("candidate_profile_id"),
        "candidate_review_packet_created": report.get("candidate_review_packet_created"),
        "candidate_profile_review_packet_id": report.get("candidate_profile_review_packet_id"),
        "approval_packet_draft_created": report.get("approval_packet_draft_created"),
        "approval_packet_created": False,
        "approval_intake_submitted": False,
        "approval_intake_status": report.get("approval_intake_status"),
        "manual_approval_readiness_status": report.get("manual_approval_readiness_status"),
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
        "signed_testnet_unlock_allowed": False,
        "testnet_order_submission_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "created_at_utc": report.get("created_at_utc") or utc_now_canonical(),
    }
    registry_record["phase4_4_registry_record_sha256"] = sha256_json(registry_record)
    persisted = append_registry_record(
        registry_path(cfg, PHASE4_4_REGISTRY_NAME),
        registry_record,
        registry_name=PHASE4_4_REGISTRY_NAME,
        id_field="phase4_4_registry_record_id",
        hash_field="phase4_4_registry_record_sha256",
        id_prefix="phase4_4_registry",
    )
    atomic_write_json(latest / "phase4_4_candidate_profile_review_packet_registry_record.json", persisted)
    report["phase4_4_registry_record_id"] = persisted.get("phase4_4_registry_record_id")
    report["phase4_4_registry_record_sha256"] = persisted.get("phase4_4_registry_record_sha256")
    atomic_write_json(latest / "phase4_4_candidate_profile_review_packet_report.json", report)
    atomic_write_json(phase_dir / "phase4_4_candidate_profile_review_packet_report.json", report)
    return report


def run_phase4_4_candidate_profile_review_packet_latest(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    return persist_phase4_4_candidate_profile_review_packet_report(cfg=cfg)
