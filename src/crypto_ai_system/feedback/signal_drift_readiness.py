from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.common import (
    bool_value as _bool,
    float_value as _float,
    hash_latest as _hash_latest,
    latest_dir as _latest_dir,
    read_latest_json as _read_latest_json,
    storage_dir as _storage_dir,
    text_value as _text,
)
from crypto_ai_system.feedback.outcome_analytics_v2 import summarize_outcomes
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

PHASE4_2_VERSION = "phase4_2_signal_drift_candidate_readiness_v1"
PHASE4_2_REGISTRY_NAME = "phase4_2_signal_drift_candidate_readiness_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE4_2_SIGNAL_DRIFT_CANDIDATE_READINESS_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE4_2_SIGNAL_DRIFT_CANDIDATE_READINESS_BLOCKED_REVIEW_ONLY"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
SETTINGS_WRITE_PREVIEW_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False
SIGNED_TESTNET_PROMOTION_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False


def _read_outcomes(cfg: AppConfig) -> list[dict[str, Any]]:
    payload = _read_latest_json(cfg, "paper_outcome_sample_accumulation_outcomes.json")
    rows = payload.get("outcomes")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _unsafe_side_effect(row: Mapping[str, Any]) -> bool:
    return any(
        _bool(row.get(name))
        for name in [
            "runtime_settings_mutated",
            "score_weights_mutated",
            "candidate_profile_applied",
            "settings_write_preview_applied",
            "approval_packet_created",
            "auto_promotion_allowed",
            "live_trading_allowed_by_this_module",
            "live_order_executed",
            "external_order_submission_performed",
            "signed_testnet_promotion_allowed",
            "testnet_order_submission_allowed_by_this_module",
            "adapter_called",
        ]
    )


def _drift_value(row: Mapping[str, Any]) -> float:
    return max(0.0, _float(row.get("signal_to_outcome_drift"), 0.0))


def _drift_bucket(row: Mapping[str, Any], *, drift_threshold: float) -> str:
    drift = _drift_value(row)
    if drift <= 0:
        return "no_drift"
    if drift <= drift_threshold:
        return "partial_drift"
    return "high_drift"


def _signal_score_bucket(row: Mapping[str, Any]) -> str:
    # Phase4.1 outcome rows do not yet carry a numeric ResearchSignal score.
    # Keep the bucket explicit rather than fabricating a signal score.
    for key in ["final_signal_score", "signal_score", "research_signal_score"]:
        value = row.get(key)
        if value not in {None, ""}:
            score = _float(value)
            if score <= -0.35:
                return "bearish_score"
            if score >= 0.35:
                return "bullish_score"
            return "neutral_score"
    return "missing_signal_score"


def _with_derived_fields(rows: Iterable[Mapping[str, Any]], *, drift_threshold: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["drift_bucket"] = _drift_bucket(item, drift_threshold=drift_threshold)
        item["signal_score_bucket"] = _signal_score_bucket(item)
        item["timeframe"] = _text(item.get("timeframe") or item.get("primary_timeframe"), "unknown")
        item["regime_direction"] = f"{_text(item.get('regime'))}:{_text(item.get('direction'))}"
        out.append(item)
    return out


def _summary(rows: list[Mapping[str, Any]], *, drift_threshold: float) -> dict[str, Any]:
    base = summarize_outcomes(rows)
    closed = [row for row in rows if row.get("outcome_closed") is True]
    drifted = [row for row in closed if _drift_value(row) > drift_threshold]
    wins = [row for row in closed if _float(row.get("result_R"), 0.0) > 0]
    losses = [row for row in closed if _float(row.get("result_R"), 0.0) < 0]
    base.update(
        {
            "sample_size": len(rows),
            "closed_count": len(closed),
            "drift_threshold": drift_threshold,
            "drifted_closed_count": len(drifted),
            "drift_rate": round(len(drifted) / len(closed), 8) if closed else 0.0,
            "win_rate": round(len(wins) / len(closed), 8) if closed else 0.0,
            "loss_rate": round(len(losses) / len(closed), 8) if closed else 0.0,
            "unsafe_side_effect_count": sum(1 for row in rows if _unsafe_side_effect(row)),
            "reconciliation_mismatch_count": sum(1 for row in rows if row.get("reconciliation_mismatch") is True),
        }
    )
    return base


def _group_by(rows: list[Mapping[str, Any]], key: str, *, drift_threshold: float) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_text(row.get(key)), []).append(row)
    return {name: _summary(list(values), drift_threshold=drift_threshold) for name, values in sorted(groups.items())}


def _readiness_subset_candidates(
    rows: list[Mapping[str, Any]],
    *,
    min_subset_sample_size: int,
    max_drift_rate: float,
    min_expectancy: float,
    max_drawdown_limit: float,
    drift_threshold: float,
) -> list[dict[str, Any]]:
    # Use only pre-trade dimensions for candidate readiness. Do not use close_reason,
    # result bucket, or other post-outcome labels as eligibility filters.
    candidates: list[dict[str, Any]] = []
    for dimension in ["direction", "regime", "regime_direction", "timeframe"]:
        grouped = _group_by(rows, dimension, drift_threshold=drift_threshold)
        for value, summary in grouped.items():
            if int(summary.get("closed_count", 0)) < min_subset_sample_size:
                continue
            if _float(summary.get("expectancy"), 0.0) <= min_expectancy:
                continue
            if _float(summary.get("drift_rate"), 1.0) > max_drift_rate:
                continue
            if _float(summary.get("max_drawdown"), 999.0) > max_drawdown_limit:
                continue
            if int(summary.get("unsafe_side_effect_count", 0)) > 0:
                continue
            if int(summary.get("reconciliation_mismatch_count", 0)) > 0:
                continue
            candidates.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "summary": summary,
                    "candidate_readiness": "LOW_DRIFT_REVIEW_ONLY_SUBSET",
                    "runtime_permission_source": False,
                    "paper_candidate_created": False,
                    "approval_packet_created": False,
                }
            )
    return sorted(candidates, key=lambda item: (-_float(item["summary"].get("expectancy"), 0.0), item["dimension"], item["value"]))


def _blockers(
    *,
    outcomes: list[Mapping[str, Any]],
    phase4_1: Mapping[str, Any],
    performance_report: Mapping[str, Any],
    overall_summary: Mapping[str, Any],
    subset_candidates: list[Mapping[str, Any]],
    min_closed_sample_size: int,
    max_drift_rate: float,
) -> list[str]:
    blockers: list[str] = []
    if not outcomes:
        blockers.append("PAPER_OUTCOME_SAMPLES_MISSING")
    if phase4_1.get("status") != "PHASE4_1_PAPER_OUTCOME_SAMPLE_ACCUMULATION_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE4_1_SAMPLE_ACCUMULATION_NOT_RECORDED")
    if performance_report.get("status") != "PERFORMANCE_REPORT_RECORDED":
        blockers.append("PERFORMANCE_REPORT_NOT_RECORDED")
    if int(overall_summary.get("closed_count", 0)) < min_closed_sample_size:
        blockers.append("INSUFFICIENT_CLOSED_OUTCOME_SAMPLE")
    if int(overall_summary.get("unsafe_side_effect_count", 0)) > 0:
        blockers.append("UNSAFE_SIDE_EFFECT_FLAG_DETECTED")
    if int(overall_summary.get("reconciliation_mismatch_count", 0)) > 0:
        blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    if _float(overall_summary.get("drift_rate"), 0.0) > max_drift_rate:
        blockers.append("OVERALL_SIGNAL_DRIFT_RATE_ABOVE_LIMIT")
    if _float(overall_summary.get("signal_to_outcome_drift"), 0.0) > 0:
        blockers.append("SIGNAL_TO_OUTCOME_DRIFT_OBSERVED")
    if not subset_candidates:
        blockers.append("NO_LOW_DRIFT_PRE_TRADE_SUBSET_READY")
    if any(_signal_score_bucket(row) == "missing_signal_score" for row in outcomes):
        blockers.append("SIGNAL_SCORE_BUCKET_MISSING_FOR_READINESS")
    return sorted(dict.fromkeys(blockers))


def build_phase4_2_signal_drift_candidate_readiness_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    min_closed_sample_size: int = 30,
    min_subset_sample_size: int = 10,
    drift_threshold: float = 0.0,
    max_drift_rate: float = 0.25,
    min_expectancy: float = 0.0,
    max_drawdown_limit: float = 6.0,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    raw_outcomes = _read_outcomes(cfg)
    outcomes = _with_derived_fields(raw_outcomes, drift_threshold=drift_threshold)
    phase4_1 = _read_latest_json(cfg, "phase4_1_paper_outcome_sample_accumulation_report.json")
    performance_report = _read_latest_json(cfg, "performance_report.json")
    phase4_feedback = _read_latest_json(cfg, "phase4_outcome_candidate_feedback_report.json")

    overall = _summary(outcomes, drift_threshold=drift_threshold)
    grouped = {
        "by_direction": _group_by(outcomes, "direction", drift_threshold=drift_threshold),
        "by_regime": _group_by(outcomes, "regime", drift_threshold=drift_threshold),
        "by_regime_direction": _group_by(outcomes, "regime_direction", drift_threshold=drift_threshold),
        "by_timeframe": _group_by(outcomes, "timeframe", drift_threshold=drift_threshold),
        "by_signal_score_bucket": _group_by(outcomes, "signal_score_bucket", drift_threshold=drift_threshold),
        "by_drift_bucket": _group_by(outcomes, "drift_bucket", drift_threshold=drift_threshold),
        "by_close_reason_review_only_not_candidate_filter": _group_by(outcomes, "close_reason", drift_threshold=drift_threshold),
    }
    subset_candidates = _readiness_subset_candidates(
        outcomes,
        min_subset_sample_size=min_subset_sample_size,
        max_drift_rate=max_drift_rate,
        min_expectancy=min_expectancy,
        max_drawdown_limit=max_drawdown_limit,
        drift_threshold=drift_threshold,
    )
    blockers = _blockers(
        outcomes=outcomes,
        phase4_1=phase4_1,
        performance_report=performance_report,
        overall_summary=overall,
        subset_candidates=subset_candidates,
        min_closed_sample_size=min_closed_sample_size,
        max_drift_rate=max_drift_rate,
    )
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    created = utc_now_canonical()
    source_artifacts = {
        name: {
            "path": str(latest / name),
            "exists": (latest / name).exists(),
            "sha256": _hash_latest(cfg, name),
        }
        for name in [
            "paper_outcome_sample_accumulation_outcomes.json",
            "phase4_1_paper_outcome_sample_accumulation_report.json",
            "performance_report.json",
            "phase4_outcome_candidate_feedback_report.json",
            "candidate_profile.json",
            "settings_write_preview_guard_manifest.json",
        ]
    }
    seed = {
        "version": PHASE4_2_VERSION,
        "source_outcome_count": len(outcomes),
        "phase4_1_id": phase4_1.get("phase4_1_paper_outcome_sample_accumulation_id"),
        "performance_report_id": performance_report.get("performance_report_id"),
        "status": status,
        "created_at_utc": created,
    }
    payload: dict[str, Any] = {
        "phase4_2_signal_drift_candidate_readiness_id": stable_id("phase4_2_signal_drift_candidate_readiness", seed, 24),
        "phase4_2_version": PHASE4_2_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "candidate_readiness_status": "CANDIDATE_READINESS_BLOCKED_REVIEW_ONLY" if blocked else "CANDIDATE_READINESS_RECORDED_REVIEW_ONLY",
        "candidate_profile_created": False,
        "candidate_profile_applied": False,
        "paper_candidate_created": False,
        "approval_packet_created": False,
        "approval_packet_ready": False,
        "settings_write_preview_applied": False,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "live_execution_unlock_authority": False,
        "min_closed_sample_size": min_closed_sample_size,
        "min_subset_sample_size": min_subset_sample_size,
        "drift_threshold": drift_threshold,
        "max_drift_rate": max_drift_rate,
        "min_expectancy": min_expectancy,
        "max_drawdown_limit": max_drawdown_limit,
        "phase4_1_status": phase4_1.get("status"),
        "performance_report_status": performance_report.get("status"),
        "performance_recommendation": performance_report.get("recommendation"),
        "phase4_feedback_status": phase4_feedback.get("status"),
        "source_outcome_count": len(outcomes),
        "overall_summary": overall,
        "grouped_summaries": grouped,
        "readiness_subset_candidates": subset_candidates,
        "readiness_subset_count": len(subset_candidates),
        "readiness_blockers": blockers,
        "recommended_next_action": "review_signal_drift_and_replay_more_paper" if blocked else "prepare_review_only_candidate_profile_draft",
        "candidate_filter_policy": {
            "uses_pre_trade_dimensions_only": True,
            "allowed_candidate_dimensions": ["direction", "regime", "regime_direction", "timeframe"],
            "post_outcome_dimensions_excluded_from_candidate_filter": ["close_reason", "drift_bucket", "result_R"],
            "missing_signal_score_policy": "block_candidate_readiness_until_signal_score_bucket_is_available",
        },
        "source_artifacts": source_artifacts,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "signed_testnet_promotion_allowed": False,
        "testnet_order_submission_allowed_by_this_module": False,
        "created_at_utc": created,
    }
    payload["phase4_2_report_sha256"] = sha256_json(payload)
    return payload


def persist_phase4_2_signal_drift_candidate_readiness_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    min_closed_sample_size: int = 30,
    min_subset_sample_size: int = 10,
    drift_threshold: float = 0.0,
    max_drift_rate: float = 0.25,
    min_expectancy: float = 0.0,
    max_drawdown_limit: float = 6.0,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    report = build_phase4_2_signal_drift_candidate_readiness_report(
        cfg=cfg,
        min_closed_sample_size=min_closed_sample_size,
        min_subset_sample_size=min_subset_sample_size,
        drift_threshold=drift_threshold,
        max_drift_rate=max_drift_rate,
        min_expectancy=min_expectancy,
        max_drawdown_limit=max_drawdown_limit,
    )
    phase_dir = _storage_dir(cfg, "storage/phase4_2_signal_drift_candidate_readiness")
    atomic_write_json(latest / "phase4_2_signal_drift_candidate_readiness_report.json", report)
    atomic_write_json(phase_dir / "phase4_2_signal_drift_candidate_readiness_report.json", report)
    registry_record = {
        "phase4_2_registry_version": PHASE4_2_VERSION,
        "phase4_2_signal_drift_candidate_readiness_id": report.get("phase4_2_signal_drift_candidate_readiness_id"),
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "candidate_readiness_status": report.get("candidate_readiness_status"),
        "source_outcome_count": report.get("source_outcome_count"),
        "overall_drift_rate": (report.get("overall_summary") or {}).get("drift_rate"),
        "readiness_subset_count": report.get("readiness_subset_count"),
        "readiness_blockers": report.get("readiness_blockers"),
        "phase4_2_report_sha256": report.get("phase4_2_report_sha256"),
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "signed_testnet_promotion_allowed": False,
        "testnet_order_submission_allowed_by_this_module": False,
        "created_at_utc": report.get("created_at_utc") or utc_now_canonical(),
    }
    registry_record["phase4_2_registry_record_sha256"] = sha256_json(registry_record)
    persisted = append_registry_record(
        registry_path(cfg, PHASE4_2_REGISTRY_NAME),
        registry_record,
        registry_name=PHASE4_2_REGISTRY_NAME,
        id_field="phase4_2_signal_drift_candidate_readiness_registry_record_id",
        hash_field="phase4_2_signal_drift_candidate_readiness_registry_record_sha256",
        id_prefix="phase4_2_signal_drift_candidate_readiness_registry",
    )
    atomic_write_json(latest / "phase4_2_signal_drift_candidate_readiness_registry_record.json", persisted)
    report["phase4_2_signal_drift_candidate_readiness_registry_record_id"] = persisted.get("phase4_2_signal_drift_candidate_readiness_registry_record_id")
    report["phase4_2_signal_drift_candidate_readiness_registry_record_sha256"] = persisted.get("phase4_2_signal_drift_candidate_readiness_registry_record_sha256")
    atomic_write_json(latest / "phase4_2_signal_drift_candidate_readiness_report.json", report)
    atomic_write_json(phase_dir / "phase4_2_signal_drift_candidate_readiness_report.json", report)
    return report


def run_phase4_2_signal_drift_candidate_readiness_latest(cfg: AppConfig | None = None) -> dict[str, Any]:
    return persist_phase4_2_signal_drift_candidate_readiness_report(cfg=cfg)
