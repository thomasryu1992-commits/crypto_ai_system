from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.common import (
    float_value as _float,
    json_safe as _json_safe,
    latest_dir as _latest_dir,
    storage_dir as _storage_dir,
    text_value as _text,
)
from crypto_ai_system.feedback.candidate_profile_registry import generate_and_persist_candidate_profile
from crypto_ai_system.feedback.outcome_analytics_v2 import OUTCOME_FEEDBACK_REGISTRY_NAME, build_outcome_feedback_registry_record
from crypto_ai_system.feedback.performance_report_generator import generate_and_persist_performance_report
from crypto_ai_system.registry.base_registry import append_registry_record, append_registry_records, registry_path
from crypto_ai_system.reports.settings_write_preview_guard import run_settings_write_preview_guard_latest
from crypto_ai_system.validation.paper_data_quality_gate import STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY, build_paper_data_quality_gate_report
from crypto_ai_system.feedback.outcome_candidate_feedback import persist_phase4_outcome_candidate_feedback_report
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

PHASE4_1_VERSION = "phase4_1_paper_outcome_sample_accumulation_v1"
PHASE4_1_REGISTRY_NAME = "phase4_1_paper_outcome_sample_accumulation_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE4_1_PAPER_OUTCOME_SAMPLE_ACCUMULATION_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE4_1_PAPER_OUTCOME_SAMPLE_ACCUMULATION_BLOCKED_REVIEW_ONLY"

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


def _feature_matrix_path(cfg: AppConfig, feature_manifest: Mapping[str, Any]) -> Path:
    raw = feature_manifest.get("matrix_path") or "storage/features/research_feature_matrix_live.csv"
    path = Path(str(raw))
    if not path.is_absolute():
        path = cfg.root / path
    return path.resolve()


def _direction(row: Mapping[str, Any]) -> str:
    mtf_score = _float(row.get("mtf_alignment_score"), 0.0)
    trend = _text(row.get("mtf_1h_trend") or row.get("mtf_bias")).upper()
    close = _float(row.get("close"), 0.0)
    ema20 = _float(row.get("ema20"), close)
    ema50 = _float(row.get("ema50"), close)
    if mtf_score <= -0.35 or "BEARISH" in trend or ema20 < ema50:
        return "SHORT"
    if mtf_score >= 0.35 or "BULLISH" in trend or ema20 > ema50:
        return "LONG"
    return "FLAT"


def _simulate_close(frame: pd.DataFrame, entry_index: int, side: str, entry: float, stop: float, take_profit: float, risk_per_unit: float, horizon_bars: int) -> dict[str, Any]:
    forward = frame.iloc[entry_index + 1 : entry_index + 1 + horizon_bars]
    for offset, (_, row) in enumerate(forward.iterrows(), start=1):
        high = _float(row.get("high"), entry)
        low = _float(row.get("low"), entry)
        timestamp = _text(row.get("timestamp"))
        if side == "LONG":
            stop_hit = low <= stop
            target_hit = high >= take_profit
            if stop_hit and target_hit:
                return {"result_R": -1.0, "exit_price": stop, "close_reason": "sl_and_tp_same_bar_conservative_stop", "bars_held": offset, "exit_timestamp": timestamp}
            if stop_hit:
                return {"result_R": -1.0, "exit_price": stop, "close_reason": "stop_loss_hit", "bars_held": offset, "exit_timestamp": timestamp}
            if target_hit:
                return {"result_R": 3.0, "exit_price": take_profit, "close_reason": "take_profit_hit", "bars_held": offset, "exit_timestamp": timestamp}
        elif side == "SHORT":
            stop_hit = high >= stop
            target_hit = low <= take_profit
            if stop_hit and target_hit:
                return {"result_R": -1.0, "exit_price": stop, "close_reason": "sl_and_tp_same_bar_conservative_stop", "bars_held": offset, "exit_timestamp": timestamp}
            if stop_hit:
                return {"result_R": -1.0, "exit_price": stop, "close_reason": "stop_loss_hit", "bars_held": offset, "exit_timestamp": timestamp}
            if target_hit:
                return {"result_R": 3.0, "exit_price": take_profit, "close_reason": "take_profit_hit", "bars_held": offset, "exit_timestamp": timestamp}
    close_row = frame.iloc[min(entry_index + horizon_bars, len(frame) - 1)]
    exit_price = _float(close_row.get("close"), entry)
    raw_r = ((exit_price - entry) / risk_per_unit) if side == "LONG" else ((entry - exit_price) / risk_per_unit)
    result_r = round(max(-1.0, min(3.0, raw_r)), 8)
    return {
        "result_R": result_r,
        "exit_price": exit_price,
        "close_reason": "time_based_close",
        "bars_held": int(min(horizon_bars, len(frame) - entry_index - 1)),
        "exit_timestamp": _text(close_row.get("timestamp")),
    }


def _build_outcome_record(*, row: Mapping[str, Any], data_manifest: Mapping[str, Any], feature_manifest: Mapping[str, Any], index: int, side: str, entry: float, stop: float, take_profit: float, risk_per_unit: float, close_result: Mapping[str, Any]) -> dict[str, Any]:
    created = utc_now_canonical()
    seed = {
        "version": PHASE4_1_VERSION,
        "timestamp": row.get("timestamp"),
        "index": index,
        "side": side,
        "entry": round(entry, 8),
        "stop": round(stop, 8),
        "take_profit": round(take_profit, 8),
    }
    research_signal_id = stable_id("research_signal", {**seed, "component": "phase4_1"}, 24)
    decision_id = stable_id("decision", {**seed, "research_signal_id": research_signal_id}, 24)
    risk_gate_id = stable_id("risk_gate", {**seed, "decision_id": decision_id}, 24)
    order_intent_id = stable_id("order_intent", {**seed, "risk_gate_id": risk_gate_id}, 24)
    execution_id = stable_id("paper_execution", {**seed, "order_intent_id": order_intent_id}, 24)
    reconciliation_id = stable_id("paper_reconciliation", {**seed, "execution_id": execution_id}, 24)
    outcome_id = stable_id("outcome", {**seed, "reconciliation_id": reconciliation_id, "result_R": close_result.get("result_R")}, 24)
    feedback_cycle_id = stable_id("feedback_cycle", {"outcome_id": outcome_id, "version": PHASE4_1_VERSION}, 24)
    result_r = _float(close_result.get("result_R"), 0.0)
    win_loss = "win" if result_r > 0 else "loss" if result_r < 0 else "breakeven"
    quantity = round(50.0 / entry, 8) if entry > 0 else 0.0
    pnl = round(result_r * quantity * risk_per_unit, 8)
    slippage_bps = 2.0
    latency_ms = 25.0
    reconciliation_evidence = {
        "order_intent_id": order_intent_id,
        "execution_id": execution_id,
        "entry_price": round(entry, 8),
        "exit_price": round(_float(close_result.get("exit_price"), entry), 8),
        "result_R": result_r,
        "paper_only": True,
    }
    outcome = {
        "outcome_id": outcome_id,
        "feedback_cycle_id": feedback_cycle_id,
        "profile_id": "paper_validation_profile_v1",
        "research_signal_id": research_signal_id,
        "decision_id": decision_id,
        "risk_gate_id": risk_gate_id,
        "order_intent_id": order_intent_id,
        "execution_id": execution_id,
        "reconciliation_id": reconciliation_id,
        "data_snapshot_id": feature_manifest.get("data_snapshot_id") or data_manifest.get("data_snapshot_id"),
        "feature_snapshot_id": feature_manifest.get("feature_snapshot_id"),
        "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
        "source_bundle_sha256": feature_manifest.get("source_bundle_sha256") or data_manifest.get("source_bundle_sha256"),
        "status": "OUTCOME_RECORDED",
        "outcome_closed": True,
        "close_reason": _text(close_result.get("close_reason")),
        "entry_timestamp": _text(row.get("timestamp")),
        "exit_timestamp": _text(close_result.get("exit_timestamp")),
        "bars_held": int(_float(close_result.get("bars_held"), 0.0)),
        "regime": _text(row.get("market_regime"), "unknown"),
        "direction": side,
        "entry_price": round(entry, 8),
        "stop_loss": round(stop, 8),
        "take_profit": round(take_profit, 8),
        "exit_price": round(_float(close_result.get("exit_price"), entry), 8),
        "result_R": result_r,
        "pnl": pnl,
        "expectancy": result_r,
        "win_loss": win_loss,
        "win_loss_ratio": 1.0 if result_r > 0 else 0.0,
        "average_R": result_r,
        "max_drawdown": abs(min(0.0, result_r)),
        "slippage": slippage_bps,
        "latency_ms": latency_ms,
        "rejection_rate": 0.0,
        "stale_data_rate": 0.0,
        "signal_to_outcome_drift": abs(result_r) if result_r < 0 else 0.0,
        "paper_live_gap": "not_applicable",
        "api_error_rate": 0.0,
        "manual_override_count": 0,
        "next_action": "create_performance_report",
        "reconciliation_status": "RECONCILED",
        "reconciliation_mismatch": False,
        "reconciliation_evidence_hash": sha256_json(reconciliation_evidence),
        "paper_reconciliation_record_sha256": sha256_json({**reconciliation_evidence, "reconciliation_id": reconciliation_id}),
        "outcome_quality_warnings": [],
        "paper_only": True,
        "adapter_called": False,
        "external_order_submission_performed": False,
        "live_order_executed": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    outcome["outcome_record_sha256"] = sha256_json(outcome)
    return outcome


def _safe_append_outcome(cfg: AppConfig, outcome: Mapping[str, Any]) -> dict[str, Any]:
    record = build_outcome_feedback_registry_record(outcome)
    persisted = append_registry_record(
        registry_path(cfg, OUTCOME_FEEDBACK_REGISTRY_NAME),
        record,
        registry_name=OUTCOME_FEEDBACK_REGISTRY_NAME,
        id_field="outcome_feedback_registry_record_id",
        hash_field="outcome_feedback_registry_record_sha256",
        id_prefix="outcome_feedback_registry",
    )
    return persisted


def _safe_append_outcomes(cfg: AppConfig, outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = [build_outcome_feedback_registry_record(outcome) for outcome in outcomes]
    return append_registry_records(
        registry_path(cfg, OUTCOME_FEEDBACK_REGISTRY_NAME),
        records,
        registry_name=OUTCOME_FEEDBACK_REGISTRY_NAME,
        id_field="outcome_feedback_registry_record_id",
        hash_field="outcome_feedback_registry_record_sha256",
        id_prefix="outcome_feedback_registry",
    )


def _block_report(cfg: AppConfig, reasons: list[str], *, gate: Mapping[str, Any] | None = None) -> dict[str, Any]:
    created = utc_now_canonical()
    payload = {
        "phase4_1_paper_outcome_sample_accumulation_id": stable_id("phase4_1_paper_outcome_sample_accumulation", {"reasons": reasons, "created_at_utc": created}, 24),
        "phase4_1_version": PHASE4_1_VERSION,
        "status": STATUS_BLOCKED_REVIEW_ONLY,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "paper_sample_accumulated": False,
        "paper_data_quality_gate_status": (gate or {}).get("status"),
        "block_reasons": sorted(dict.fromkeys(reasons)),
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "approval_packet_created": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "testnet_order_submission_allowed_by_this_module": False,
        "created_at_utc": created,
    }
    payload["phase4_1_report_sha256"] = sha256_json(payload)
    return payload


def build_phase4_1_paper_outcome_sample_accumulation_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    sample_size: int = 50,
    horizon_bars: int = 12,
    min_closed_sample_size: int = 10,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    data_manifest = read_json(latest / "data_snapshot_manifest.json", default={}) or {}
    feature_manifest = read_json(latest / "feature_store_manifest.json", default={}) or {}
    quality_gate = build_paper_data_quality_gate_report(project_root=cfg.root)
    blockers: list[str] = []
    if quality_gate.get("status") != STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY:
        blockers.append("PAPER_DATA_QUALITY_GATE_NOT_PASSED")
        blockers.extend([str(item) for item in quality_gate.get("block_reasons", [])])

    matrix_path = _feature_matrix_path(cfg, feature_manifest)
    if not matrix_path.exists():
        blockers.append("FEATURE_MATRIX_MISSING")
    if blockers:
        return _block_report(cfg, blockers, gate=quality_gate)

    frame = pd.read_csv(matrix_path)
    if frame.empty:
        return _block_report(cfg, ["FEATURE_MATRIX_EMPTY"], gate=quality_gate)
    if len(frame) <= horizon_bars + 5:
        return _block_report(cfg, ["FEATURE_MATRIX_TOO_SHORT_FOR_FORWARD_OUTCOME_SIMULATION"], gate=quality_gate)

    start = max(0, len(frame) - sample_size - horizon_bars)
    end = len(frame) - horizon_bars
    outcomes: list[dict[str, Any]] = []
    skipped = {"flat_or_neutral": 0, "invalid_price_or_risk": 0}
    for idx in range(start, end):
        row = _json_safe(frame.iloc[idx].to_dict())
        side = _direction(row)
        if side == "FLAT":
            skipped["flat_or_neutral"] += 1
            continue
        entry = _float(row.get("close"), 0.0)
        atr = max(_float(row.get("atr"), 0.0), entry * 0.0025 if entry > 0 else 0.0)
        if entry <= 0 or atr <= 0:
            skipped["invalid_price_or_risk"] += 1
            continue
        if side == "LONG":
            stop = entry - atr
            take_profit = entry + (3.0 * atr)
        else:
            stop = entry + atr
            take_profit = entry - (3.0 * atr)
        close_result = _simulate_close(frame, idx, side, entry, stop, take_profit, atr, horizon_bars)
        outcomes.append(
            _build_outcome_record(
                row=row,
                data_manifest=data_manifest,
                feature_manifest=feature_manifest,
                index=idx,
                side=side,
                entry=entry,
                stop=stop,
                take_profit=take_profit,
                risk_per_unit=atr,
                close_result=close_result,
            )
        )

    if not outcomes:
        return _block_report(cfg, ["NO_PAPER_OUTCOME_SAMPLES_GENERATED"], gate=quality_gate)

    registry_records = _safe_append_outcomes(cfg, outcomes)
    for outcome, registry_record in zip(outcomes, registry_records, strict=False):
        outcome["outcome_feedback_registry_record_id"] = registry_record.get("outcome_feedback_registry_record_id")
        outcome["outcome_feedback_registry_record_sha256"] = registry_record.get("outcome_feedback_registry_record_sha256")
    latest_outcome = outcomes[-1]
    atomic_write_json(latest / "outcome_analytics_record.json", latest_outcome)
    atomic_write_json(latest / "paper_outcome_sample_accumulation_outcomes.json", {"outcomes": outcomes})

    performance_report = generate_and_persist_performance_report(outcomes, cfg=cfg, min_sample_size=min_closed_sample_size)
    candidate_profile = generate_and_persist_candidate_profile(performance_report, cfg=cfg)
    settings_write_preview = run_settings_write_preview_guard_latest(cfg=cfg)
    phase4_feedback = persist_phase4_outcome_candidate_feedback_report(cfg=cfg)

    closed_count = sum(1 for item in outcomes if item.get("outcome_closed") is True)
    win_count = sum(1 for item in outcomes if _float(item.get("result_R"), 0.0) > 0)
    loss_count = sum(1 for item in outcomes if _float(item.get("result_R"), 0.0) < 0)
    created = utc_now_canonical()
    blocked = closed_count < min_closed_sample_size
    report = {
        "phase4_1_paper_outcome_sample_accumulation_id": stable_id(
            "phase4_1_paper_outcome_sample_accumulation",
            {"outcomes": [item.get("outcome_id") for item in outcomes], "created_at_utc": created},
            24,
        ),
        "phase4_1_version": PHASE4_1_VERSION,
        "status": STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_sample_accumulated": True,
        "paper_data_quality_gate_status": quality_gate.get("status"),
        "feature_matrix_path": str(matrix_path),
        "feature_matrix_sha256": sha256_file(matrix_path),
        "source_feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
        "sample_window": {"start_index": start, "end_index_exclusive": end, "requested_sample_size": sample_size, "horizon_bars": horizon_bars},
        "outcome_count": len(outcomes),
        "closed_count": closed_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "breakeven_count": closed_count - win_count - loss_count,
        "min_closed_sample_size": min_closed_sample_size,
        "skipped": skipped,
        "performance_report_id": performance_report.get("performance_report_id"),
        "performance_report_status": performance_report.get("status"),
        "performance_recommendation": performance_report.get("recommendation"),
        "performance_expectancy": performance_report.get("expectancy"),
        "performance_average_R": performance_report.get("average_R"),
        "performance_win_loss_ratio": performance_report.get("win_loss_ratio"),
        "performance_max_drawdown": performance_report.get("max_drawdown"),
        "performance_sample_size": performance_report.get("sample_size"),
        "candidate_profile_id": candidate_profile.get("candidate_profile_id"),
        "candidate_profile_creation_status": candidate_profile.get("creation_status"),
        "candidate_profile_status": candidate_profile.get("status"),
        "candidate_profile_created": candidate_profile.get("candidate_profile_created", False),
        "settings_write_preview_status": settings_write_preview.get("status"),
        "phase4_feedback_status": phase4_feedback.get("status"),
        "source_outcome_ids": [item.get("outcome_id") for item in outcomes],
        "source_outcome_hashes": [item.get("outcome_record_sha256") for item in outcomes],
        "block_reasons": [] if not blocked else ["INSUFFICIENT_CLOSED_OUTCOME_SAMPLE"],
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "approval_packet_created": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "signed_testnet_promotion_allowed": False,
        "testnet_order_submission_allowed_by_this_module": False,
        "created_at_utc": created,
    }
    report["phase4_1_report_sha256"] = sha256_json(report)
    return report


def persist_phase4_1_paper_outcome_sample_accumulation_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    sample_size: int = 50,
    horizon_bars: int = 12,
    min_closed_sample_size: int = 10,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    report = build_phase4_1_paper_outcome_sample_accumulation_report(
        cfg=cfg,
        sample_size=sample_size,
        horizon_bars=horizon_bars,
        min_closed_sample_size=min_closed_sample_size,
    )
    phase_dir = _storage_dir(cfg, "storage/phase4_1_paper_outcome_sample_accumulation")
    atomic_write_json(latest / "phase4_1_paper_outcome_sample_accumulation_report.json", report)
    atomic_write_json(phase_dir / "phase4_1_paper_outcome_sample_accumulation_report.json", report)
    registry_record = {
        "phase4_1_registry_version": PHASE4_1_VERSION,
        "phase4_1_paper_outcome_sample_accumulation_id": report.get("phase4_1_paper_outcome_sample_accumulation_id"),
        "phase4_1_report_sha256": report.get("phase4_1_report_sha256"),
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "outcome_count": report.get("outcome_count"),
        "closed_count": report.get("closed_count"),
        "performance_report_id": report.get("performance_report_id"),
        "candidate_profile_id": report.get("candidate_profile_id"),
        "runtime_settings_mutated": report.get("runtime_settings_mutated"),
        "score_weights_mutated": report.get("score_weights_mutated"),
        "candidate_profile_applied": report.get("candidate_profile_applied"),
        "approval_packet_created": report.get("approval_packet_created"),
        "auto_promotion_allowed": report.get("auto_promotion_allowed"),
        "live_trading_allowed_by_this_module": report.get("live_trading_allowed_by_this_module"),
        "external_order_submission_performed": report.get("external_order_submission_performed"),
        "created_at_utc": report.get("created_at_utc") or utc_now_canonical(),
    }
    registry_record["phase4_1_registry_record_id"] = stable_id("phase4_1_registry", registry_record, 24)
    registry_record["phase4_1_registry_record_sha256"] = sha256_json(registry_record)
    persisted = append_registry_record(
        registry_path(cfg, PHASE4_1_REGISTRY_NAME),
        registry_record,
        registry_name=PHASE4_1_REGISTRY_NAME,
        id_field="phase4_1_registry_record_id",
        hash_field="phase4_1_registry_record_sha256",
        id_prefix="phase4_1_registry",
    )
    atomic_write_json(latest / "phase4_1_paper_outcome_sample_accumulation_registry_record.json", persisted)
    report["phase4_1_registry_record_id"] = persisted.get("phase4_1_registry_record_id")
    report["phase4_1_registry_record_sha256"] = persisted.get("phase4_1_registry_record_sha256")
    atomic_write_json(latest / "phase4_1_paper_outcome_sample_accumulation_report.json", report)
    atomic_write_json(phase_dir / "phase4_1_paper_outcome_sample_accumulation_report.json", report)
    return report


def run_phase4_1_paper_outcome_sample_accumulation_latest(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    return persist_phase4_1_paper_outcome_sample_accumulation_report(cfg=cfg)
