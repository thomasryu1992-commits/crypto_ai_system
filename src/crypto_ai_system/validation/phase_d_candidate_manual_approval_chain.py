from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.approval_registry import (
    STATUS_APPROVAL_VALID_REVIEW_ONLY,
    VALIDATION_STATUS_VALID,
    build_and_persist_approval_registry_record,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_file, sha256_json, stable_id, utc_now_canonical

PHASE_D_VERSION = "phase_d_candidate_manual_approval_chain_v1"
PHASE_D_REGISTRY_NAME = "phase_d_candidate_manual_approval_chain_registry"

STATUS_PHASE_D_VALID_REVIEW_ONLY = "PHASE_D_CANDIDATE_MANUAL_APPROVAL_CHAIN_VALID_REVIEW_ONLY"
STATUS_PHASE_D_BLOCKED_REVIEW_ONLY = "PHASE_D_CANDIDATE_MANUAL_APPROVAL_CHAIN_BLOCKED_REVIEW_ONLY"

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
SIGNED_TESTNET_UNLOCK_AUTHORITY_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False
APPROVAL_FILE_AUTO_REGENERATED_BY_THIS_MODULE = False

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "signed_testnet_unlock_authority",
    "signed_testnet_unlock_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "auto_promotion_allowed",
    "live_trading_allowed",
    "live_trading_allowed_by_this_module",
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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_truthy_fields(payload: Mapping[str, Any]) -> list[str]:
    return [field for field in UNSAFE_TRUTHY_FIELDS if _bool(payload.get(field))]


def _unsafe_flags_by_artifact(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name, payload in artifacts.items():
        flags = _unsafe_truthy_fields(payload)
        if flags:
            found[name] = flags
    return found


def _embed_hash(payload: Mapping[str, Any], field: str, aliases: set[str] | None = None) -> dict[str, Any]:
    result = dict(payload or {})
    exclude = {field}
    if aliases:
        exclude.update(aliases)
    result[field] = sha256_json({k: v for k, v in result.items() if k not in exclude})
    return result


def _source_report_file_sha256(cfg: AppConfig, path_text: str) -> str | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.is_absolute():
        path = cfg.root / path
    if not path.exists() or path.is_dir():
        return None
    return sha256_file(path)


def _source_report_path_from_phase_c(phase_c: Mapping[str, Any]) -> str:
    # Use the Phase C report itself as the source report for Phase D approval review.
    # The approval registry validates this by hashing the file bytes, not by trusting
    # any embedded report hash.
    return "storage/latest/phase_c_paper_operation_validation_report.json"


def _artifact_ready_blockers(
    *,
    cfg: AppConfig,
    phase_c: Mapping[str, Any],
    phase4_4: Mapping[str, Any],
    candidate_review_packet: Mapping[str, Any],
    approval_draft: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if phase_c.get("status") != "PHASE_C_PAPER_OPERATION_VALIDATION_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE_C_PAPER_OPERATION_VALIDATION_NOT_READY")
    if phase_c.get("paper_operation_loop_validated") is not True:
        blockers.append("PHASE_C_PAPER_LOOP_NOT_VALIDATED")
    if phase_c.get("candidate_profile_ready_for_manual_review") is not True:
        blockers.append("PHASE_C_CANDIDATE_PROFILE_NOT_READY_FOR_MANUAL_REVIEW")
    if phase_c.get("runtime_permission_source") is not False:
        blockers.append("PHASE_C_RUNTIME_PERMISSION_NOT_FALSE")
    if phase4_4.get("status") != "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE4_4_CANDIDATE_REVIEW_PACKET_REPORT_NOT_READY")
    if phase4_4.get("candidate_review_packet_created") is not True:
        blockers.append("PHASE4_4_CANDIDATE_REVIEW_PACKET_NOT_CREATED")
    if not candidate_review_packet:
        blockers.append("CANDIDATE_PROFILE_REVIEW_PACKET_MISSING")
    if candidate_review_packet.get("profile_candidate_hash_valid") is not True:
        blockers.append("CANDIDATE_PROFILE_HASH_NOT_VALID")
    if not _text(candidate_review_packet.get("candidate_profile_id")):
        blockers.append("CANDIDATE_PROFILE_ID_MISSING")
    if not _text(candidate_review_packet.get("profile_candidate_hash")):
        blockers.append("PROFILE_CANDIDATE_HASH_MISSING")
    if not _text(candidate_review_packet.get("feature_matrix_sha256")):
        blockers.append("FEATURE_MATRIX_HASH_MISSING")
    if approval_draft.get("status") != "APPROVAL_PACKET_DRAFT_REVIEW_ONLY_NOT_APPROVED":
        blockers.append("APPROVAL_PACKET_DRAFT_NOT_READY")
    if approval_draft.get("validation_status") != "NOT_SUBMITTED_REVIEW_ONLY":
        blockers.append("APPROVAL_PACKET_DRAFT_VALIDATION_STATUS_NOT_REVIEW_ONLY")
    if approval_draft.get("approval_packet_created") is not False:
        blockers.append("APPROVAL_PACKET_DRAFT_CREATED_FLAG_NOT_FALSE")
    if approval_draft.get("approval_packet_id") is not None:
        blockers.append("APPROVAL_PACKET_DRAFT_ALREADY_HAS_PACKET_ID")
    if approval_draft.get("approval_intake_id") is not None:
        blockers.append("APPROVAL_PACKET_DRAFT_ALREADY_HAS_INTAKE_ID")

    source_path = _source_report_path_from_phase_c(phase_c)
    if _source_report_file_sha256(cfg, source_path) is None:
        blockers.append("PHASE_C_SOURCE_REPORT_FILE_MISSING_OR_UNHASHABLE")

    unsafe = _unsafe_flags_by_artifact(
        {
            "phase_c": phase_c,
            "phase4_4": phase4_4,
            "candidate_review_packet": candidate_review_packet,
            "approval_draft": approval_draft,
        }
    )
    for artifact, fields in unsafe.items():
        blockers.append(f"UNSAFE_TRUTHY_FLAG:{artifact}:{','.join(fields)}")
    return sorted(dict.fromkeys(blockers))


def build_manual_approval_candidate_profile_accepted_draft(
    *,
    cfg: AppConfig,
    phase_c: Mapping[str, Any],
    candidate_review_packet: Mapping[str, Any],
) -> dict[str, Any]:
    source_report_path = _source_report_path_from_phase_c(phase_c)
    source_report_hash = _source_report_file_sha256(cfg, source_report_path)
    created = utc_now_canonical()
    payload = {
        "candidate_profile_version": "phase_d_manual_approval_candidate_profile_accepted_draft_v1",
        "candidate_profile_created": True,
        "candidate_profile_id": candidate_review_packet.get("candidate_profile_id"),
        "status": "approval_packet_ready",
        "approval_review_status": "accepted_for_review",
        "source_report_id": phase_c.get("phase_c_paper_operation_validation_id"),
        "source_report_path": source_report_path,
        "source_report_hash": source_report_hash,
        "source_report_registry_record_id": phase_c.get("phase_c_paper_operation_validation_registry_record_id"),
        "source_report_registry_record_sha256": phase_c.get("phase_c_paper_operation_validation_registry_record_sha256"),
        "profile_version": candidate_review_packet.get("profile_version"),
        "strategy_family": "research_signal_feedback_v1",
        "target_timeframe": candidate_review_packet.get("target_timeframe") or "review_only",
        "allowed_direction": candidate_review_packet.get("allowed_direction") or "review_only",
        "feature_matrix_sha256": candidate_review_packet.get("feature_matrix_sha256"),
        "source_bundle_sha256": candidate_review_packet.get("source_bundle_sha256"),
        "data_snapshot_id": candidate_review_packet.get("data_snapshot_id"),
        "feature_snapshot_id": candidate_review_packet.get("feature_snapshot_id"),
        "profile_candidate_hash": candidate_review_packet.get("profile_candidate_hash"),
        "paper_operation_loop_validated": phase_c.get("paper_operation_loop_validated") is True,
        "closed_paper_outcome_sample_count": phase_c.get("closed_paper_outcome_sample_count"),
        "score_bucket_alignment_drift_rate": (phase_c.get("performance_metrics") or {}).get("score_bucket_alignment_drift_rate"),
        "reconciliation_mismatch_count": (phase_c.get("performance_metrics") or {}).get("reconciliation_mismatch_count"),
        "manual_approval_required": True,
        "manual_approval_chain_stage": "phase_d_review_only",
        "live_ineligible_reason": "accepted_for_review_only_manual_approval_chain_does_not_grant_runtime_permission",
        "review_only": True,
        "paper_candidate": True,
        "approval_packet_ready": True,
        "candidate_profile_applied": CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE,
        "approval_packet_created": False,
        "settings_write_preview_created": False,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
        "auto_promotion_allowed": AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE,
        "signed_testnet_unlock_authority": SIGNED_TESTNET_UNLOCK_AUTHORITY_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE,
        "created_at_utc": created,
    }
    payload["phase_d_candidate_profile_accepted_draft_id"] = stable_id("phase_d_candidate_profile", payload, 24)
    payload["phase_d_candidate_profile_accepted_draft_sha256"] = sha256_json(payload)
    return payload


def build_phase_d_approval_packet_candidate(
    *,
    cfg: AppConfig,
    accepted_candidate: Mapping[str, Any],
    phase_c: Mapping[str, Any],
    candidate_review_packet: Mapping[str, Any],
    approval_draft: Mapping[str, Any],
) -> dict[str, Any]:
    source_report_path = _source_report_path_from_phase_c(phase_c)
    created = utc_now_canonical()
    seed = {
        "candidate_profile_id": accepted_candidate.get("candidate_profile_id"),
        "profile_candidate_hash": accepted_candidate.get("profile_candidate_hash"),
        "source_report_hash": accepted_candidate.get("source_report_hash"),
        "feature_matrix_hash": accepted_candidate.get("feature_matrix_sha256"),
        "created_at_utc": created,
    }
    packet = {
        "approval_packet_version": "phase_d_manual_approval_packet_candidate_v1",
        "approval_packet_id": stable_id("approval_packet", seed, 24),
        "status": "APPROVAL_PACKET_CANDIDATE_REVIEW_ONLY_VALIDATION_READY",
        "validation_status": "AWAITING_OR_VALIDATED_MANUAL_INTAKE_REVIEW_ONLY",
        "review_only": True,
        "paper_only": True,
        "manual_approval_required": True,
        "manual_approval_packet_type": "candidate_profile_to_signed_testnet_runtime_review_prerequisite",
        "source_phase_c_report_id": phase_c.get("phase_c_paper_operation_validation_id"),
        "source_phase_c_report_sha256": phase_c.get("phase_c_report_sha256"),
        "source_report_path": source_report_path,
        "source_report_hash": accepted_candidate.get("source_report_hash") or _source_report_file_sha256(cfg, source_report_path),
        "candidate_profile_review_packet_id": candidate_review_packet.get("candidate_profile_review_packet_id"),
        "candidate_profile_review_packet_sha256": candidate_review_packet.get("candidate_profile_review_packet_sha256"),
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "approval_packet_draft_sha256": approval_draft.get("approval_packet_draft_sha256"),
        "candidate_profile_id": accepted_candidate.get("candidate_profile_id"),
        "profile_candidate_hash": accepted_candidate.get("profile_candidate_hash"),
        "feature_matrix_hash": accepted_candidate.get("feature_matrix_sha256"),
        "feature_matrix_sha256": accepted_candidate.get("feature_matrix_sha256"),
        "source_bundle_sha256": accepted_candidate.get("source_bundle_sha256"),
        "data_snapshot_id": accepted_candidate.get("data_snapshot_id"),
        "feature_snapshot_id": accepted_candidate.get("feature_snapshot_id"),
        "required_manual_fields": [
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
        "must_remain_false_before_separate_runtime_boundary": [
            "ready_for_signed_testnet_execution",
            "testnet_order_submission_allowed",
            "signed_testnet_promotion_allowed",
            "external_order_submission_allowed",
            "external_order_submission_performed",
            "place_order_enabled",
            "cancel_order_enabled",
            "signed_order_executor_enabled",
            "live_canary_execution_enabled",
            "live_scaled_execution_enabled",
        ],
        "approval_file_auto_regenerated": False,
        "approval_packet_created_by_this_module": False,
        "candidate_profile_applied": CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
        "auto_promotion_allowed": AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE,
        "signed_testnet_promotion_allowed": False,
        "signed_testnet_unlock_authority": SIGNED_TESTNET_UNLOCK_AUTHORITY_BY_THIS_MODULE,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "created_at_utc": created,
    }
    return _embed_hash(packet, "approval_packet_hash", {"approval_packet_sha256"})


def build_phase_d_manual_approval_intake_fixture(
    *,
    approval_packet: Mapping[str, Any],
    approver_info: str = "operator_fixture_review_only:manual_chain_validation",
    ticket_or_signature: str = "ticket_fixture_review_only:PHASE_D_MANUAL_APPROVAL_CHAIN",
) -> dict[str, Any]:
    created = utc_now_canonical()
    seed = {
        "approval_packet_id": approval_packet.get("approval_packet_id"),
        "profile_candidate_hash": approval_packet.get("profile_candidate_hash"),
        "approver_info": approver_info,
        "created_at_utc": created,
    }
    intake = {
        "approval_intake_version": "phase_d_manual_approval_intake_fixture_v1",
        "approval_intake_id": stable_id("approval_intake", seed, 24),
        "approval_packet_id": approval_packet.get("approval_packet_id"),
        "approval_packet_hash": approval_packet.get("approval_packet_hash"),
        "approver_info": approver_info,
        "ticket_or_signature": ticket_or_signature,
        "source_report_hash": approval_packet.get("source_report_hash"),
        "feature_matrix_hash": approval_packet.get("feature_matrix_hash") or approval_packet.get("feature_matrix_sha256"),
        "profile_candidate_hash": approval_packet.get("profile_candidate_hash"),
        "canonical_utc_timestamp": created,
        "manual_operator_submitted": True,
        "manual_fixture_review_only": True,
        "approval_file_auto_regenerated": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "signed_testnet_unlock_authority": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": created,
    }
    return _embed_hash(intake, "approval_intake_hash", {"approval_intake_sha256"})


def _manual_intake_blockers(intake: Mapping[str, Any]) -> list[str]:
    if not intake:
        return ["MANUAL_APPROVAL_INTAKE_MISSING"]
    required = [
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
    blockers = [f"MANUAL_APPROVAL_INTAKE_FIELD_MISSING:{field}" for field in required if not _text(intake.get(field))]
    if _text(intake.get("canonical_utc_timestamp")) and not is_canonical_utc_timestamp(_text(intake.get("canonical_utc_timestamp"))):
        blockers.append("MANUAL_APPROVAL_INTAKE_TIMESTAMP_NOT_CANONICAL_UTC")
    unsafe = _unsafe_truthy_fields(intake)
    if unsafe:
        blockers.append("MANUAL_APPROVAL_INTAKE_UNSAFE_TRUTHY_FLAGS:" + ",".join(unsafe))
    return sorted(dict.fromkeys(blockers))


def build_phase_d_candidate_manual_approval_chain_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    create_manual_fixture: bool = True,
    approval_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_c = _read_latest_json(cfg, "phase_c_paper_operation_validation_report.json")
    phase4_4 = _read_latest_json(cfg, "phase4_4_candidate_profile_review_packet_report.json")
    candidate_review_packet = _read_latest_json(cfg, "candidate_profile_review_packet.json")
    approval_draft = _read_latest_json(cfg, "approval_packet_draft_review_only.json")

    artifact_blockers = _artifact_ready_blockers(
        cfg=cfg,
        phase_c=phase_c,
        phase4_4=phase4_4,
        candidate_review_packet=candidate_review_packet,
        approval_draft=approval_draft,
    )

    accepted_candidate: dict[str, Any] = {}
    approval_packet: dict[str, Any] = {}
    intake: dict[str, Any] = dict(approval_intake or {})
    approval_registry_record: dict[str, Any] = {}

    if not artifact_blockers:
        accepted_candidate = build_manual_approval_candidate_profile_accepted_draft(
            cfg=cfg,
            phase_c=phase_c,
            candidate_review_packet=candidate_review_packet,
        )
        approval_packet = build_phase_d_approval_packet_candidate(
            cfg=cfg,
            accepted_candidate=accepted_candidate,
            phase_c=phase_c,
            candidate_review_packet=candidate_review_packet,
            approval_draft=approval_draft,
        )
        if not intake and create_manual_fixture:
            intake = build_phase_d_manual_approval_intake_fixture(approval_packet=approval_packet)

    manual_blockers = _manual_intake_blockers(intake) if not artifact_blockers else []

    if accepted_candidate:
        atomic_write_json(latest / "manual_approval_candidate_profile_accepted_draft.json", accepted_candidate)
    if approval_packet:
        atomic_write_json(latest / "approval_packet_candidate.json", approval_packet)
    if intake:
        atomic_write_json(latest / "approval_intake_record.json", intake)
        manual_dir = _storage_dir(cfg, "storage/manual_approval")
        atomic_write_json(manual_dir / "approval_intake_submission.json", intake)

    if accepted_candidate and approval_packet:
        source_report_for_registry = Path(str(approval_packet.get("source_report_path") or ""))
        if source_report_for_registry and not source_report_for_registry.is_absolute():
            source_report_for_registry = cfg.root / source_report_for_registry
        approval_registry_record = build_and_persist_approval_registry_record(
            accepted_candidate,
            approval_packet,
            intake,
            cfg=cfg,
            source_report_path=source_report_for_registry,
            approval_packet_path=latest / "approval_packet_candidate.json",
            approval_intake_path=(latest / "approval_intake_record.json") if intake else None,
        )

    registry_valid = (
        approval_registry_record.get("approval_registry_status") == STATUS_APPROVAL_VALID_REVIEW_ONLY
        and approval_registry_record.get("validation_status") == VALIDATION_STATUS_VALID
    )
    block_reasons = sorted(
        dict.fromkeys(
            [*artifact_blockers, *manual_blockers, *list(approval_registry_record.get("blocked_reasons") or [])]
        )
    )
    blocked = bool(block_reasons) or not registry_valid
    if not block_reasons and not registry_valid:
        block_reasons.append("APPROVAL_REGISTRY_NOT_VALID_REVIEW_ONLY")
        blocked = True

    created = utc_now_canonical()
    canonical_id_chain = {
        "data_snapshot_id": accepted_candidate.get("data_snapshot_id"),
        "feature_snapshot_id": accepted_candidate.get("feature_snapshot_id"),
        "research_signal_id": phase_c.get("canonical_id_chain", {}).get("research_signal_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
        "profile_id": accepted_candidate.get("candidate_profile_id"),
        "approval_packet_id": approval_packet.get("approval_packet_id"),
        "approval_intake_id": intake.get("approval_intake_id"),
        "decision_id": phase_c.get("canonical_id_chain", {}).get("decision_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
        "risk_gate_id": phase_c.get("canonical_id_chain", {}).get("risk_gate_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
        "order_intent_id": phase_c.get("canonical_id_chain", {}).get("order_intent_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
        "execution_id": phase_c.get("canonical_id_chain", {}).get("execution_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
        "reconciliation_id": phase_c.get("canonical_id_chain", {}).get("reconciliation_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
        "outcome_id": phase_c.get("canonical_id_chain", {}).get("outcome_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
        "feedback_cycle_id": phase_c.get("canonical_id_chain", {}).get("feedback_cycle_id") if isinstance(phase_c.get("canonical_id_chain"), Mapping) else None,
    }
    required_phase_d_fields = [
        "data_snapshot_id",
        "feature_snapshot_id",
        "research_signal_id",
        "profile_id",
        "approval_packet_id",
        "approval_intake_id",
        "decision_id",
        "risk_gate_id",
        "order_intent_id",
        "execution_id",
        "reconciliation_id",
        "outcome_id",
        "feedback_cycle_id",
    ]
    missing_chain_fields = [field for field in required_phase_d_fields if not _text(canonical_id_chain.get(field))]

    report = {
        "phase_d_candidate_manual_approval_chain_id": stable_id(
            "phase_d_candidate_manual_approval_chain",
            {
                "approval_packet_id": approval_packet.get("approval_packet_id"),
                "approval_intake_id": intake.get("approval_intake_id"),
                "created_at_utc": created,
            },
            24,
        ),
        "phase_d_version": PHASE_D_VERSION,
        "status": STATUS_PHASE_D_BLOCKED_REVIEW_ONLY if blocked else STATUS_PHASE_D_VALID_REVIEW_ONLY,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "manual_fixture_used": bool(intake.get("manual_fixture_review_only")),
        "candidate_profile_accepted_draft_created": bool(accepted_candidate),
        "candidate_profile_approval_review_status": accepted_candidate.get("approval_review_status"),
        "candidate_profile_status": accepted_candidate.get("status"),
        "approval_packet_candidate_created": bool(approval_packet),
        "approval_intake_submitted": bool(intake),
        "manual_intake_required_fields_present": bool(intake) and not manual_blockers,
        "approval_registry_valid_review_outcome": registry_valid,
        "approval_registry_status": approval_registry_record.get("approval_registry_status"),
        "approval_registry_validation_status": approval_registry_record.get("validation_status"),
        "approval_registry_record_id": approval_registry_record.get("approval_registry_record_id"),
        "approval_registry_record_sha256": approval_registry_record.get("approval_registry_record_sha256"),
        "hash_chain_validation": approval_registry_record.get("hash_chain_validation") or {},
        "approval_packet_id": approval_packet.get("approval_packet_id"),
        "approval_intake_id": intake.get("approval_intake_id"),
        "approver_info_present": bool(_text(intake.get("approver_info"))),
        "ticket_or_signature_present": bool(_text(intake.get("ticket_or_signature"))),
        "canonical_utc_timestamp_valid": is_canonical_utc_timestamp(_text(intake.get("canonical_utc_timestamp"))) if intake else False,
        "source_report_hash": accepted_candidate.get("source_report_hash") or approval_packet.get("source_report_hash"),
        "feature_matrix_hash": accepted_candidate.get("feature_matrix_sha256") or approval_packet.get("feature_matrix_hash"),
        "profile_candidate_hash": accepted_candidate.get("profile_candidate_hash") or approval_packet.get("profile_candidate_hash"),
        "canonical_id_chain": canonical_id_chain,
        "phase_d_canonical_id_chain_complete": not missing_chain_fields,
        "missing_phase_d_canonical_id_chain_fields": missing_chain_fields,
        "block_reasons": block_reasons,
        "source_artifacts": {
            "phase_c_report": {
                "present": bool(phase_c),
                "status": phase_c.get("status"),
                "sha256": phase_c.get("phase_c_report_sha256"),
            },
            "phase4_4_report": {
                "present": bool(phase4_4),
                "status": phase4_4.get("status"),
                "sha256": phase4_4.get("phase4_4_report_sha256"),
            },
            "candidate_profile_review_packet": {
                "present": bool(candidate_review_packet),
                "sha256": candidate_review_packet.get("candidate_profile_review_packet_sha256"),
            },
            "approval_packet_draft": {
                "present": bool(approval_draft),
                "sha256": approval_draft.get("approval_packet_draft_sha256"),
            },
        },
        "live_candidate_eligible": False,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": SIGNED_TESTNET_UNLOCK_AUTHORITY_BY_THIS_MODULE,
        "signed_testnet_promotion_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE,
        "live_execution_unlock_authority": False,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
        "candidate_profile_applied": CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE,
        "auto_promotion_allowed": AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "approval_file_auto_regenerated": APPROVAL_FILE_AUTO_REGENERATED_BY_THIS_MODULE,
        "recommended_next_action": "design_separate_signed_testnet_one_order_runtime_package_still_disabled",
        "created_at_utc": created,
    }
    report["phase_d_report_sha256"] = sha256_json({k: v for k, v in report.items() if k != "phase_d_report_sha256"})
    return report


def persist_phase_d_candidate_manual_approval_chain_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    create_manual_fixture: bool = True,
    approval_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    report = build_phase_d_candidate_manual_approval_chain_report(
        cfg=cfg,
        create_manual_fixture=create_manual_fixture,
        approval_intake=approval_intake,
    )
    latest = _latest_dir(cfg)
    atomic_write_json(latest / "phase_d_candidate_manual_approval_chain_report.json", report)
    archive_dir = _storage_dir(cfg, "storage/phase_d_candidate_manual_approval_chain")
    atomic_write_json(archive_dir / "phase_d_candidate_manual_approval_chain_report.json", report)
    record = append_registry_record(
        registry_path(cfg, PHASE_D_REGISTRY_NAME),
        report,
        registry_name=PHASE_D_REGISTRY_NAME,
        id_field="phase_d_candidate_manual_approval_chain_registry_record_id",
        hash_field="phase_d_candidate_manual_approval_chain_registry_record_sha256",
        id_prefix="phase_d_candidate_manual_approval_chain_registry",
    )
    atomic_write_json(latest / "phase_d_candidate_manual_approval_chain_registry_record.json", record)
    summary = {
        "phase": "P3/Phase D - Candidate and Manual Approval Chain",
        "status": report.get("status"),
        "approval_registry_valid_review_outcome": report.get("approval_registry_valid_review_outcome"),
        "approval_registry_validation_status": report.get("approval_registry_validation_status"),
        "approval_packet_id": report.get("approval_packet_id"),
        "approval_intake_id": report.get("approval_intake_id"),
        "manual_fixture_used": report.get("manual_fixture_used"),
        "runtime_permission_source": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "created_at_utc": report.get("created_at_utc"),
    }
    atomic_write_json(latest / "p3_candidate_manual_approval_chain_summary.json", summary)
    return report
