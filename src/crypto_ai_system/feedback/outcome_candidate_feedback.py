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
    storage_dir as _storage_dir,
    text_value as _text,
)
from crypto_ai_system.feedback.candidate_profile_registry import run_candidate_profile_latest
from crypto_ai_system.feedback.performance_report_generator import run_performance_report_latest
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.reports.settings_write_preview_guard import run_settings_write_preview_guard_latest
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

PHASE4_OUTCOME_CANDIDATE_FEEDBACK_VERSION = "phase4_outcome_candidate_feedback_v1"
PHASE4_OUTCOME_CANDIDATE_FEEDBACK_REGISTRY = "phase4_outcome_candidate_feedback_registry"

STATUS_PHASE4_RECORDED_REVIEW_ONLY = "PHASE4_OUTCOME_CANDIDATE_RECORDED_REVIEW_ONLY"
STATUS_PHASE4_BLOCKED_REVIEW_ONLY = "PHASE4_OUTCOME_CANDIDATE_BLOCKED_REVIEW_ONLY"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
SETTINGS_WRITE_PREVIEW_APPLIED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False
SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False


def _unsafe_side_effect(payload: Mapping[str, Any]) -> bool:
    return any(
        _bool(payload.get(name))
        for name in [
            "runtime_settings_mutated",
            "score_weights_mutated",
            "candidate_profile_applied",
            "approval_packet_created",
            "settings_write_preview_applied",
            "auto_promotion_allowed",
            "live_trading_allowed_by_this_module",
            "live_order_executed",
            "external_order_submission_performed",
            "signed_testnet_promotion_allowed",
            "testnet_order_submission_allowed_by_this_module",
        ]
    )


def _collect_blockers(
    *,
    paper_strategy_validation: Mapping[str, Any],
    outcome: Mapping[str, Any],
    performance_report: Mapping[str, Any],
    candidate_profile: Mapping[str, Any],
    settings_write_preview: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not paper_strategy_validation:
        blockers.append("PAPER_STRATEGY_VALIDATION_MISSING")
    if not outcome:
        blockers.append("OUTCOME_RECORD_MISSING")
    if not performance_report:
        blockers.append("PERFORMANCE_REPORT_MISSING")
    if not candidate_profile:
        blockers.append("CANDIDATE_PROFILE_MISSING")
    if not settings_write_preview:
        blockers.append("SETTINGS_WRITE_PREVIEW_MISSING")

    for label, payload in [
        ("paper_strategy_validation", paper_strategy_validation),
        ("outcome", outcome),
        ("performance_report", performance_report),
        ("candidate_profile", candidate_profile),
        ("settings_write_preview", settings_write_preview),
    ]:
        if payload and _unsafe_side_effect(payload):
            blockers.append(f"UNSAFE_SIDE_EFFECT_FLAG_DETECTED:{label}")

    perf_status = _text(performance_report.get("status"))
    perf_recommendation = _text(performance_report.get("recommendation"))
    if perf_status != "PERFORMANCE_REPORT_RECORDED" or perf_recommendation != "create_candidate_profile_draft":
        blockers.append("PERFORMANCE_REPORT_NOT_READY_FOR_CANDIDATE_PROFILE")

    if candidate_profile.get("candidate_profile_created") is not True:
        blockers.append("CANDIDATE_PROFILE_NOT_CREATED")
    if _text(candidate_profile.get("status")) not in {"review_only", "paper_candidate", "approval_packet_ready"}:
        blockers.append("CANDIDATE_PROFILE_NOT_REVIEW_READY")
    if candidate_profile.get("paper_candidate") is True or candidate_profile.get("approval_packet_ready") is True:
        blockers.append("CANDIDATE_PROFILE_ESCALATED_BEYOND_REVIEW_ONLY")

    preview_status = _text(settings_write_preview.get("status"))
    if not preview_status.startswith("SETTINGS_WRITE_PREVIEW_CREATED"):
        blockers.append("SETTINGS_WRITE_PREVIEW_NOT_CREATED")
    if settings_write_preview.get("runtime_settings_mutated") is True:
        blockers.append("SETTINGS_WRITE_PREVIEW_MUTATED_RUNTIME_SETTINGS")
    if settings_write_preview.get("score_weights_mutated") is True:
        blockers.append("SETTINGS_WRITE_PREVIEW_MUTATED_SCORE_WEIGHTS")

    return sorted(dict.fromkeys(blockers))


def build_phase4_outcome_candidate_feedback_report(
    *,
    cfg: AppConfig | None = None,
    performance_report: Mapping[str, Any] | None = None,
    candidate_profile: Mapping[str, Any] | None = None,
    settings_write_preview: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    latest = _latest_dir(cfg)
    paper_strategy_validation = _read_latest_json(cfg, "paper_strategy_validation_report.json")
    outcome = _read_latest_json(cfg, "outcome_analytics_record.json")
    performance = dict(performance_report or _read_latest_json(cfg, "performance_report.json"))
    candidate = dict(candidate_profile or _read_latest_json(cfg, "candidate_profile.json"))
    preview = dict(settings_write_preview or _read_latest_json(cfg, "settings_write_preview_guard_manifest.json"))

    blockers = _collect_blockers(
        paper_strategy_validation=paper_strategy_validation,
        outcome=outcome,
        performance_report=performance,
        candidate_profile=candidate,
        settings_write_preview=preview,
    )
    blocked = bool(blockers)
    status = STATUS_PHASE4_BLOCKED_REVIEW_ONLY if blocked else STATUS_PHASE4_RECORDED_REVIEW_ONLY
    created = utc_now_canonical()

    source_artifacts = {
        name: {
            "path": str(latest / name),
            "exists": (latest / name).exists(),
            "sha256": _hash_latest(cfg, name),
        }
        for name in [
            "paper_strategy_validation_report.json",
            "outcome_analytics_record.json",
            "performance_report.json",
            "candidate_profile.json",
            "settings_write_preview_guard_manifest.json",
        ]
    }

    report_seed = {
        "version": PHASE4_OUTCOME_CANDIDATE_FEEDBACK_VERSION,
        "paper_strategy_validation_id": paper_strategy_validation.get("paper_strategy_validation_id"),
        "outcome_id": outcome.get("outcome_id"),
        "performance_report_id": performance.get("performance_report_id"),
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "settings_write_preview_guard_id": preview.get("settings_write_preview_guard_id"),
        "status": status,
        "created_at_utc": created,
    }

    payload: dict[str, Any] = {
        "phase4_outcome_candidate_feedback_id": stable_id("phase4_outcome_candidate_feedback", report_seed, 24),
        "phase4_outcome_candidate_feedback_version": PHASE4_OUTCOME_CANDIDATE_FEEDBACK_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_strategy_validation_status": paper_strategy_validation.get("status"),
        "paper_strategy_next_action": paper_strategy_validation.get("next_action"),
        "outcome_id": outcome.get("outcome_id"),
        "outcome_status": outcome.get("status"),
        "outcome_closed": outcome.get("outcome_closed"),
        "result_R": outcome.get("result_R"),
        "pnl": outcome.get("pnl"),
        "expectancy": outcome.get("expectancy"),
        "win_loss_ratio": outcome.get("win_loss_ratio"),
        "average_R": outcome.get("average_R"),
        "max_drawdown": outcome.get("max_drawdown"),
        "slippage": outcome.get("slippage"),
        "latency_ms": outcome.get("latency_ms"),
        "rejection_rate": outcome.get("rejection_rate"),
        "stale_data_rate": outcome.get("stale_data_rate"),
        "signal_to_outcome_drift": outcome.get("signal_to_outcome_drift"),
        "paper_live_gap": outcome.get("paper_live_gap"),
        "api_error_rate": outcome.get("api_error_rate"),
        "manual_override_count": outcome.get("manual_override_count"),
        "performance_report_id": performance.get("performance_report_id"),
        "performance_report_status": performance.get("status"),
        "performance_recommendation": performance.get("recommendation"),
        "performance_sample_size": performance.get("sample_size"),
        "performance_closed_count": performance.get("closed_count"),
        "performance_failure_modes": performance.get("failure_modes", []),
        "performance_blockers": performance.get("blockers", []),
        "summary_by_profile": performance.get("summary_by_profile", {}),
        "summary_by_signal": performance.get("summary_by_signal", {}),
        "summary_by_regime": performance.get("summary_by_regime", {}),
        "summary_by_direction": performance.get("summary_by_direction", {}),
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "candidate_profile_created": candidate.get("candidate_profile_created", False),
        "candidate_profile_creation_status": candidate.get("creation_status"),
        "candidate_profile_status": candidate.get("status"),
        "candidate_profile_blockers": candidate.get("blockers", []),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "candidate_live_ineligible_reason": candidate.get("live_ineligible_reason"),
        "settings_write_preview_guard_id": preview.get("settings_write_preview_guard_id"),
        "settings_write_preview_status": preview.get("status"),
        "settings_write_preview_blocked_reasons": preview.get("blocked_reasons", []),
        "disabled_settings_write_preview_diff_path": preview.get("disabled_settings_write_preview_diff_path"),
        "disabled_settings_write_preview_diff_sha256": preview.get("disabled_settings_write_preview_diff_sha256"),
        "source_artifacts": source_artifacts,
        "blockers": blockers,
        "next_action": "repeat_in_paper" if blocked else "prepare_manual_approval_packet_draft_review_only",
        "live_candidate_eligible": False,
        "candidate_profile_applied": CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE,
        "approval_packet_created": APPROVAL_PACKET_CREATED_BY_THIS_MODULE,
        "settings_write_preview_applied": SETTINGS_WRITE_PREVIEW_APPLIED_BY_THIS_MODULE,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
        "auto_promotion_allowed": AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE,
        "signed_testnet_promotion_allowed": SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "testnet_order_submission_allowed_by_this_module": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE,
        "created_at_utc": created,
    }
    payload["phase4_outcome_candidate_feedback_sha256"] = sha256_json(payload)
    return payload


def build_phase4_outcome_candidate_feedback_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(report or {})
    record = {
        "phase4_outcome_candidate_feedback_registry_version": PHASE4_OUTCOME_CANDIDATE_FEEDBACK_VERSION,
        "phase4_outcome_candidate_feedback_id": payload.get("phase4_outcome_candidate_feedback_id"),
        "phase4_outcome_candidate_feedback_sha256": payload.get("phase4_outcome_candidate_feedback_sha256"),
        "status": payload.get("status"),
        "blocked": payload.get("blocked"),
        "fail_closed": payload.get("fail_closed"),
        "paper_strategy_validation_status": payload.get("paper_strategy_validation_status"),
        "outcome_id": payload.get("outcome_id"),
        "outcome_status": payload.get("outcome_status"),
        "outcome_closed": payload.get("outcome_closed"),
        "performance_report_id": payload.get("performance_report_id"),
        "performance_report_status": payload.get("performance_report_status"),
        "performance_recommendation": payload.get("performance_recommendation"),
        "performance_sample_size": payload.get("performance_sample_size"),
        "performance_closed_count": payload.get("performance_closed_count"),
        "candidate_profile_id": payload.get("candidate_profile_id"),
        "candidate_profile_created": payload.get("candidate_profile_created"),
        "candidate_profile_status": payload.get("candidate_profile_status"),
        "settings_write_preview_status": payload.get("settings_write_preview_status"),
        "blockers": payload.get("blockers", []),
        "live_candidate_eligible": payload.get("live_candidate_eligible", False),
        "runtime_settings_mutated": payload.get("runtime_settings_mutated", False),
        "score_weights_mutated": payload.get("score_weights_mutated", False),
        "auto_promotion_allowed": payload.get("auto_promotion_allowed", False),
        "external_order_submission_performed": payload.get("external_order_submission_performed", False),
        "created_at_utc": payload.get("created_at_utc") or utc_now_canonical(),
    }
    record["phase4_outcome_candidate_feedback_registry_record_id"] = stable_id("phase4_outcome_candidate_feedback_registry", record, 24)
    record["phase4_outcome_candidate_feedback_registry_record_sha256"] = sha256_json(record)
    return record


def persist_phase4_outcome_candidate_feedback_report(*, cfg: AppConfig | None = None, min_sample_size: int = 3) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    performance = run_performance_report_latest(cfg=cfg, min_sample_size=min_sample_size)
    candidate = run_candidate_profile_latest(cfg=cfg)
    preview = run_settings_write_preview_guard_latest(cfg=cfg)
    report = build_phase4_outcome_candidate_feedback_report(
        cfg=cfg,
        performance_report=performance,
        candidate_profile=candidate,
        settings_write_preview=preview,
    )
    latest = _latest_dir(cfg)
    atomic_write_json(latest / "phase4_outcome_candidate_feedback_report.json", report)
    storage_report_dir = _storage_dir(cfg, "storage/phase4_outcome_candidate_feedback")
    atomic_write_json(storage_report_dir / "phase4_outcome_candidate_feedback_report.json", report)

    registry_record = build_phase4_outcome_candidate_feedback_registry_record(report)
    persisted = append_registry_record(
        registry_path(cfg, PHASE4_OUTCOME_CANDIDATE_FEEDBACK_REGISTRY),
        registry_record,
        registry_name=PHASE4_OUTCOME_CANDIDATE_FEEDBACK_REGISTRY,
        id_field="phase4_outcome_candidate_feedback_registry_record_id",
        hash_field="phase4_outcome_candidate_feedback_registry_record_sha256",
        id_prefix="phase4_outcome_candidate_feedback_registry",
    )
    atomic_write_json(latest / "phase4_outcome_candidate_feedback_registry_record.json", persisted)
    report["phase4_outcome_candidate_feedback_registry_record_id"] = persisted.get("phase4_outcome_candidate_feedback_registry_record_id")
    report["phase4_outcome_candidate_feedback_registry_record_sha256"] = persisted.get("phase4_outcome_candidate_feedback_registry_record_sha256")
    atomic_write_json(latest / "phase4_outcome_candidate_feedback_report.json", report)
    atomic_write_json(storage_report_dir / "phase4_outcome_candidate_feedback_report.json", report)
    return report
