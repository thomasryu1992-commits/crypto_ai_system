from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

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

PHASE4_3_VERSION = "phase4_3_research_signal_score_bucket_replay_v1"
PHASE4_3_REGISTRY_NAME = "phase4_3_research_signal_score_bucket_replay_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_BLOCKED_REVIEW_ONLY"

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


def _feature_matrix_path(cfg: AppConfig, feature_manifest: Mapping[str, Any]) -> Path:
    raw = feature_manifest.get("matrix_path") or "storage/features/research_feature_matrix_live.csv"
    path = Path(str(raw))
    if not path.is_absolute():
        path = cfg.root / path
    return path.resolve()


def _read_feature_rows(cfg: AppConfig) -> tuple[dict[str, dict[str, Any]], str | None, str | None]:
    feature_manifest = _read_latest_json(cfg, "feature_store_manifest.json")
    matrix_path = _feature_matrix_path(cfg, feature_manifest)
    if not matrix_path.exists():
        return {}, None, None
    frame = pd.read_csv(matrix_path)
    rows: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        item = row.to_dict()
        timestamp = _text(item.get("timestamp"), "")
        if timestamp:
            rows[timestamp] = item
    return rows, str(matrix_path), sha256_file(matrix_path)


def _feature_score(row: Mapping[str, Any], key: str) -> float:
    return _float(row.get(key), 0.0)


def _price_direction_score(feature_row: Mapping[str, Any]) -> float:
    mtf = _feature_score(feature_row, "mtf_alignment_score")
    if mtf:
        return max(-1.0, min(1.0, mtf))
    close = _float(feature_row.get("close"), 0.0)
    ema20 = _float(feature_row.get("ema20"), close)
    ema50 = _float(feature_row.get("ema50"), close)
    if ema20 < ema50:
        return -0.5
    if ema20 > ema50:
        return 0.5
    return 0.0


def _research_signal_score(feature_row: Mapping[str, Any]) -> dict[str, Any]:
    price_direction_score = _price_direction_score(feature_row)
    derivatives_positioning_score = max(
        -1.0,
        min(
            1.0,
            (_feature_score(feature_row, "binance_derivatives_score") + _feature_score(feature_row, "extra_derivatives_score")) / 2.0,
        ),
    )
    exchange_flow_score = _feature_score(feature_row, "exchange_flow_score")
    etf_flow_score = _feature_score(feature_row, "etf_flow_score")
    stablecoin_liquidity_score = _feature_score(feature_row, "stablecoin_liquidity_score")
    final_score = round(
        (0.50 * price_direction_score)
        + (0.20 * derivatives_positioning_score)
        + (0.10 * exchange_flow_score)
        + (0.10 * etf_flow_score)
        + (0.10 * stablecoin_liquidity_score),
        8,
    )
    if final_score <= -0.35:
        bucket = "strong_bearish_score"
        permission = "allow_short_paper_only"
        expected_direction = "SHORT"
    elif final_score <= -0.10:
        bucket = "bearish_score"
        permission = "allow_short_paper_only"
        expected_direction = "SHORT"
    elif final_score < 0.10:
        bucket = "neutral_score"
        permission = "review_only_neutral"
        expected_direction = "NEUTRAL"
    elif final_score < 0.35:
        bucket = "bullish_score"
        permission = "allow_long_paper_only"
        expected_direction = "LONG"
    else:
        bucket = "strong_bullish_score"
        permission = "allow_long_paper_only"
        expected_direction = "LONG"
    optional_missing = any(
        _bool(feature_row.get(key))
        for key in [
            "extra_derivatives_features_neutral_due_to_missing",
            "exchange_flow_features_neutral_due_to_missing",
            "etf_flow_features_neutral_due_to_missing",
            "stablecoin_liquidity_features_neutral_due_to_missing",
            "missing_optional_data_neutral",
        ]
    )
    return {
        "price_direction_score": price_direction_score,
        "derivatives_positioning_score": derivatives_positioning_score,
        "exchange_flow_score": exchange_flow_score,
        "etf_flow_score": etf_flow_score,
        "stablecoin_liquidity_score": stablecoin_liquidity_score,
        "final_signal_score": final_score,
        "signal_score_bucket": bucket,
        "permission_result": permission,
        "expected_direction_from_score": expected_direction,
        "optional_missing_neutral": optional_missing,
        "live_candidate_eligible": False,
    }


def _signal_alignment_drift(outcome: Mapping[str, Any], signal: Mapping[str, Any]) -> float:
    expected = _text(signal.get("expected_direction_from_score"), "NEUTRAL").upper()
    direction = _text(outcome.get("direction"), "UNKNOWN").upper()
    if expected == "NEUTRAL":
        return 0.0
    return 0.0 if expected == direction else 1.0


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


def _enrich_outcomes(outcomes: Iterable[Mapping[str, Any]], feature_by_timestamp: Mapping[str, Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    enriched: list[dict[str, Any]] = []
    warnings: list[str] = []
    for row in outcomes:
        item = dict(row)
        timestamp = _text(item.get("entry_timestamp"), "")
        feature_row = feature_by_timestamp.get(timestamp)
        if not feature_row:
            item["signal_score_bucket"] = "missing_signal_score"
            item["score_bucket_source"] = "missing_feature_row"
            item["signal_alignment_drift"] = 1.0
            warnings.append(f"MISSING_FEATURE_ROW_FOR_OUTCOME:{item.get('outcome_id')}")
            enriched.append(item)
            continue
        signal = _research_signal_score(feature_row)
        item.update(signal)
        item["score_bucket_source"] = "feature_matrix_pre_trade_row"
        item["timeframe"] = _text(feature_row.get("timeframe"), _text(item.get("timeframe"), "unknown"))
        item["regime"] = _text(item.get("regime") or feature_row.get("market_regime"), "unknown")
        item["regime_direction"] = f"{_text(item.get('regime'))}:{_text(item.get('direction'))}"
        item["score_bucket_regime"] = f"{item['signal_score_bucket']}:{item['regime']}"
        item["score_bucket_direction"] = f"{item['signal_score_bucket']}:{item.get('direction')}"
        item["signal_alignment_drift"] = _signal_alignment_drift(item, signal)
        item["signal_to_outcome_drift"] = item["signal_alignment_drift"]
        item["research_signal_score_metadata_attached"] = True
        item["runtime_settings_mutated"] = False
        item["score_weights_mutated"] = False
        item["candidate_profile_applied"] = False
        item["approval_packet_created"] = False
        item["external_order_submission_performed"] = False
        item["live_order_executed"] = False
        enriched.append(item)
    return enriched, sorted(dict.fromkeys(warnings))


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    base = summarize_outcomes(rows)
    closed = [row for row in rows if row.get("outcome_closed") is True]
    drifted = [row for row in closed if _float(row.get("signal_alignment_drift"), 0.0) > 0.0]
    base.update(
        {
            "sample_size": len(rows),
            "closed_count": len(closed),
            "alignment_drifted_closed_count": len(drifted),
            "alignment_drift_rate": round(len(drifted) / len(closed), 8) if closed else 0.0,
            "unsafe_side_effect_count": sum(1 for row in rows if _unsafe_side_effect(row)),
            "reconciliation_mismatch_count": sum(1 for row in rows if row.get("reconciliation_mismatch") is True),
            "missing_signal_score_count": sum(1 for row in rows if _text(row.get("signal_score_bucket")) == "missing_signal_score"),
        }
    )
    return base


def _group_by(rows: list[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_text(row.get(key)), []).append(row)
    return {name: _summary(list(values)) for name, values in sorted(groups.items())}


def _candidate_subsets(
    rows: list[Mapping[str, Any]],
    *,
    min_subset_sample_size: int,
    max_alignment_drift_rate: float,
    min_expectancy: float,
    max_drawdown_limit: float,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    # All dimensions below are known before trade entry after Phase4.3 enrichment.
    for dimension in [
        "signal_score_bucket",
        "direction",
        "regime",
        "timeframe",
        "score_bucket_regime",
        "score_bucket_direction",
    ]:
        grouped = _group_by(rows, dimension)
        for value, summary in grouped.items():
            if int(summary.get("closed_count", 0)) < min_subset_sample_size:
                continue
            if _float(summary.get("expectancy"), 0.0) <= min_expectancy:
                continue
            if _float(summary.get("alignment_drift_rate"), 1.0) > max_alignment_drift_rate:
                continue
            if _float(summary.get("max_drawdown"), 999.0) > max_drawdown_limit:
                continue
            if int(summary.get("unsafe_side_effect_count", 0)) > 0:
                continue
            if int(summary.get("reconciliation_mismatch_count", 0)) > 0:
                continue
            if int(summary.get("missing_signal_score_count", 0)) > 0:
                continue
            candidates.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "summary": summary,
                    "candidate_readiness": "DRIFT_REDUCED_LOW_DRIFT_PAPER_SUBSET_REVIEW_ONLY",
                    "paper_candidate_draft_created": False,
                    "runtime_permission_source": False,
                    "approval_packet_created": False,
                    "live_candidate_eligible": False,
                }
            )
    return sorted(candidates, key=lambda item: (-_float(item["summary"].get("expectancy"), 0.0), _float(item["summary"].get("max_drawdown"), 999.0), item["dimension"], item["value"]))


def _build_candidate_profile_draft(best_subset: Mapping[str, Any] | None, *, report_id: str, feature_manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    if not best_subset:
        return None
    summary = dict(best_subset.get("summary") or {})
    created = utc_now_canonical()
    draft = {
        "candidate_profile_id": stable_id("drift_reduced_candidate_profile", {"report_id": report_id, "subset": best_subset, "created_at_utc": created}, 24),
        "profile_version": "phase4_3_drift_reduced_review_only_v1",
        "status": "review_only_draft",
        "strategy_family": "price_structure_research_signal_score_bucket_paper_replay",
        "target_timeframe": "PT1H",
        "allowed_direction": "SHORT" if "bearish" in _text(best_subset.get("value")) or _text(best_subset.get("value")) == "SHORT" else "review_required",
        "source_report_id": report_id,
        "source_dimension": best_subset.get("dimension"),
        "source_value": best_subset.get("value"),
        "expected_edge_reason": "low_alignment_drift_positive_expectancy_paper_subset",
        "data_quality_score": "review_only_valid_price_lineage_optional_missing_neutral",
        "paper_priority_score": round(_float(summary.get("expectancy"), 0.0), 8),
        "risk_complexity_score": round(_float(summary.get("max_drawdown"), 0.0), 8),
        "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
        "source_bundle_sha256": feature_manifest.get("source_bundle_sha256"),
        "sample_size": summary.get("closed_count"),
        "expectancy": summary.get("expectancy"),
        "average_R": summary.get("average_R"),
        "max_drawdown": summary.get("max_drawdown"),
        "alignment_drift_rate": summary.get("alignment_drift_rate"),
        "live_candidate_eligible": False,
        "live_ineligible_reason": "review_only_draft_requires_manual_approval_more_paper_and_optional_source_health",
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    draft["profile_candidate_hash"] = sha256_json(draft)
    return draft


def _blockers(
    *,
    raw_outcomes: list[Mapping[str, Any]],
    enriched: list[Mapping[str, Any]],
    feature_rows: Mapping[str, Mapping[str, Any]],
    phase4_2: Mapping[str, Any],
    overall: Mapping[str, Any],
    subsets: list[Mapping[str, Any]],
    min_closed_sample_size: int,
    max_alignment_drift_rate: float,
) -> list[str]:
    blockers: list[str] = []
    if not raw_outcomes:
        blockers.append("PAPER_OUTCOME_SAMPLES_MISSING")
    if not feature_rows:
        blockers.append("FEATURE_MATRIX_ROWS_MISSING_FOR_SCORE_BUCKET_REPLAY")
    if phase4_2.get("status") not in {
        "PHASE4_2_SIGNAL_DRIFT_CANDIDATE_READINESS_BLOCKED_REVIEW_ONLY",
        "PHASE4_2_SIGNAL_DRIFT_CANDIDATE_READINESS_RECORDED_REVIEW_ONLY",
    }:
        blockers.append("PHASE4_2_DRIFT_REVIEW_NOT_AVAILABLE")
    if int(overall.get("closed_count", 0)) < min_closed_sample_size:
        blockers.append("INSUFFICIENT_CLOSED_OUTCOME_SAMPLE")
    if int(overall.get("unsafe_side_effect_count", 0)) > 0:
        blockers.append("UNSAFE_SIDE_EFFECT_FLAG_DETECTED")
    if int(overall.get("reconciliation_mismatch_count", 0)) > 0:
        blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    if int(overall.get("missing_signal_score_count", 0)) > 0:
        blockers.append("SCORE_BUCKET_ATTACHMENT_INCOMPLETE")
    if _float(overall.get("alignment_drift_rate"), 1.0) > max_alignment_drift_rate and not subsets:
        blockers.append("NO_DRIFT_REDUCED_LOW_DRIFT_SUBSET_READY")
    if not subsets:
        blockers.append("NO_CANDIDATE_READY_SCORE_BUCKET_SUBSET")
    return sorted(dict.fromkeys(blockers))


def build_phase4_3_research_signal_score_bucket_replay_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    min_closed_sample_size: int = 30,
    min_subset_sample_size: int = 10,
    max_alignment_drift_rate: float = 0.25,
    min_expectancy: float = 0.0,
    max_drawdown_limit: float = 6.0,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    raw_outcomes = _read_outcomes(cfg)
    feature_rows, matrix_path, matrix_sha = _read_feature_rows(cfg)
    feature_manifest = _read_latest_json(cfg, "feature_store_manifest.json")
    phase4_1 = _read_latest_json(cfg, "phase4_1_paper_outcome_sample_accumulation_report.json")
    phase4_2 = _read_latest_json(cfg, "phase4_2_signal_drift_candidate_readiness_report.json")

    enriched, warnings = _enrich_outcomes(raw_outcomes, feature_rows)
    overall = _summary(enriched)
    grouped = {
        "by_signal_score_bucket": _group_by(enriched, "signal_score_bucket"),
        "by_direction": _group_by(enriched, "direction"),
        "by_regime": _group_by(enriched, "regime"),
        "by_timeframe": _group_by(enriched, "timeframe"),
        "by_score_bucket_regime": _group_by(enriched, "score_bucket_regime"),
        "by_score_bucket_direction": _group_by(enriched, "score_bucket_direction"),
    }
    subsets = _candidate_subsets(
        enriched,
        min_subset_sample_size=min_subset_sample_size,
        max_alignment_drift_rate=max_alignment_drift_rate,
        min_expectancy=min_expectancy,
        max_drawdown_limit=max_drawdown_limit,
    )
    blockers = _blockers(
        raw_outcomes=raw_outcomes,
        enriched=enriched,
        feature_rows=feature_rows,
        phase4_2=phase4_2,
        overall=overall,
        subsets=subsets,
        min_closed_sample_size=min_closed_sample_size,
        max_alignment_drift_rate=max_alignment_drift_rate,
    )
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    created = utc_now_canonical()
    seed = {
        "version": PHASE4_3_VERSION,
        "source_outcome_count": len(raw_outcomes),
        "readiness_subset_count": len(subsets),
        "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256") or matrix_sha,
        "status": status,
        "created_at_utc": created,
    }
    report_id = stable_id("phase4_3_research_signal_score_bucket_replay", seed, 24)
    draft = _build_candidate_profile_draft(subsets[0] if subsets else None, report_id=report_id, feature_manifest=feature_manifest)
    source_artifacts = {
        name: {
            "path": str(latest / name),
            "exists": (latest / name).exists(),
            "sha256": _hash_latest(cfg, name),
        }
        for name in [
            "paper_outcome_sample_accumulation_outcomes.json",
            "phase4_1_paper_outcome_sample_accumulation_report.json",
            "phase4_2_signal_drift_candidate_readiness_report.json",
            "feature_store_manifest.json",
            "data_snapshot_manifest.json",
        ]
    }
    payload: dict[str, Any] = {
        "phase4_3_research_signal_score_bucket_replay_id": report_id,
        "phase4_3_version": PHASE4_3_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "source_outcome_count": len(raw_outcomes),
        "enriched_outcome_count": len(enriched),
        "feature_matrix_path": matrix_path,
        "feature_matrix_sha256": matrix_sha,
        "source_feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
        "phase4_1_status": phase4_1.get("status"),
        "phase4_2_status": phase4_2.get("status"),
        "score_bucket_metadata_attached": len(warnings) == 0 and bool(enriched),
        "overall_summary": overall,
        "grouped_summaries": grouped,
        "drift_reduced_subset_candidates": subsets,
        "drift_reduced_subset_count": len(subsets),
        "candidate_readiness_status": "DRIFT_REDUCED_CANDIDATE_PROFILE_DRAFT_REVIEW_ONLY" if draft else "DRIFT_REDUCED_CANDIDATE_READINESS_BLOCKED_REVIEW_ONLY",
        "candidate_profile_draft_created": bool(draft),
        "candidate_profile_draft_id": draft.get("candidate_profile_id") if draft else None,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "approval_packet_ready": False,
        "settings_write_preview_applied": False,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "live_execution_unlock_authority": False,
        "min_closed_sample_size": min_closed_sample_size,
        "min_subset_sample_size": min_subset_sample_size,
        "max_alignment_drift_rate": max_alignment_drift_rate,
        "min_expectancy": min_expectancy,
        "max_drawdown_limit": max_drawdown_limit,
        "block_reasons": blockers,
        "warnings": warnings,
        "recommended_next_action": "prepare_manual_review_packet_after_more_paper" if draft else "adjust_signal_scoring_and_replay_more_paper",
        "candidate_filter_policy": {
            "uses_pre_trade_dimensions_only": True,
            "allowed_candidate_dimensions": ["signal_score_bucket", "direction", "regime", "timeframe", "score_bucket_regime", "score_bucket_direction"],
            "post_outcome_dimensions_excluded_from_candidate_filter": ["close_reason", "result_R", "win_loss"],
            "score_bucket_source": "feature_matrix_pre_trade_row",
            "no_runtime_permission_granted": True,
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
    payload["phase4_3_report_sha256"] = sha256_json(payload)
    return payload


def persist_phase4_3_research_signal_score_bucket_replay_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    min_closed_sample_size: int = 30,
    min_subset_sample_size: int = 10,
    max_alignment_drift_rate: float = 0.25,
    min_expectancy: float = 0.0,
    max_drawdown_limit: float = 6.0,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    report = build_phase4_3_research_signal_score_bucket_replay_report(
        cfg=cfg,
        min_closed_sample_size=min_closed_sample_size,
        min_subset_sample_size=min_subset_sample_size,
        max_alignment_drift_rate=max_alignment_drift_rate,
        min_expectancy=min_expectancy,
        max_drawdown_limit=max_drawdown_limit,
    )
    phase_dir = _storage_dir(cfg, "storage/phase4_3_research_signal_score_bucket_replay")
    atomic_write_json(latest / "phase4_3_research_signal_score_bucket_replay_report.json", report)
    atomic_write_json(phase_dir / "phase4_3_research_signal_score_bucket_replay_report.json", report)

    # Persist enriched outcomes separately to keep the source Phase4.1 outcomes immutable.
    raw_outcomes = _read_outcomes(cfg)
    feature_rows, _, _ = _read_feature_rows(cfg)
    enriched, _ = _enrich_outcomes(raw_outcomes, feature_rows)
    atomic_write_json(latest / "paper_outcome_score_bucket_enriched_outcomes.json", {"outcomes": enriched})
    atomic_write_json(phase_dir / "paper_outcome_score_bucket_enriched_outcomes.json", {"outcomes": enriched})

    draft: dict[str, Any] | None = None
    subsets = report.get("drift_reduced_subset_candidates")
    if isinstance(subsets, list) and subsets:
        draft = _build_candidate_profile_draft(
            subsets[0],
            report_id=str(report.get("phase4_3_research_signal_score_bucket_replay_id")),
            feature_manifest=_read_latest_json(cfg, "feature_store_manifest.json"),
        )
    if draft:
        atomic_write_json(latest / "drift_reduced_candidate_profile_draft.json", draft)
        atomic_write_json(phase_dir / "drift_reduced_candidate_profile_draft.json", draft)

    registry_record = {
        "phase4_3_registry_version": PHASE4_3_VERSION,
        "phase4_3_research_signal_score_bucket_replay_id": report.get("phase4_3_research_signal_score_bucket_replay_id"),
        "phase4_3_report_sha256": report.get("phase4_3_report_sha256"),
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "candidate_readiness_status": report.get("candidate_readiness_status"),
        "source_outcome_count": report.get("source_outcome_count"),
        "drift_reduced_subset_count": report.get("drift_reduced_subset_count"),
        "candidate_profile_draft_created": report.get("candidate_profile_draft_created"),
        "candidate_profile_draft_id": report.get("candidate_profile_draft_id"),
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
    registry_record["phase4_3_registry_record_sha256"] = sha256_json(registry_record)
    persisted = append_registry_record(
        registry_path(cfg, PHASE4_3_REGISTRY_NAME),
        registry_record,
        registry_name=PHASE4_3_REGISTRY_NAME,
        id_field="phase4_3_registry_record_id",
        hash_field="phase4_3_registry_record_sha256",
        id_prefix="phase4_3_registry",
    )
    atomic_write_json(latest / "phase4_3_research_signal_score_bucket_replay_registry_record.json", persisted)
    report["phase4_3_registry_record_id"] = persisted.get("phase4_3_registry_record_id")
    report["phase4_3_registry_record_sha256"] = persisted.get("phase4_3_registry_record_sha256")
    atomic_write_json(latest / "phase4_3_research_signal_score_bucket_replay_report.json", report)
    atomic_write_json(phase_dir / "phase4_3_research_signal_score_bucket_replay_report.json", report)
    return report


def run_phase4_3_research_signal_score_bucket_replay_latest(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    return persist_phase4_3_research_signal_score_bucket_replay_report(cfg=cfg)
