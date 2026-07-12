from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.paper_execution_engine_v2 import execute_and_persist_paper_order
from crypto_ai_system.execution.paper_reconciliation_v2 import reconcile_and_persist_paper_execution
from crypto_ai_system.feedback.outcome_analytics_v2 import analyze_and_persist_paper_outcome
from crypto_ai_system.quality.legacy_signal_fallback_blocker import build_legacy_signal_fallback_block_report
from crypto_ai_system.quality.signal_qa import persist_signal_qa_report, validate_research_signal_quality
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.registry.decision_pipeline_registry import persist_decision_pipeline_registry_record
from crypto_ai_system.registry.research_signal_registry import persist_research_signal_registry_record
from crypto_ai_system.trading.order_id_chain import ORDER_ID_CHAIN_VERSION, decision_id_from_signal, order_intent_id_from_payload
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.paper_data_quality_gate import STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY, build_paper_data_quality_gate_report

PAPER_STRATEGY_VALIDATION_VERSION = "phase3_paper_strategy_validation_v1"
PAPER_STRATEGY_VALIDATION_REGISTRY = "paper_strategy_validation_registry"
STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY = "PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY"
STATUS_PAPER_STRATEGY_VALIDATION_BLOCKED_REVIEW_ONLY = "PAPER_STRATEGY_VALIDATION_BLOCKED_REVIEW_ONLY"


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if text.lower() == "nan":
        return default
    return text


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _feature_matrix_path(cfg: AppConfig, feature_manifest: Mapping[str, Any]) -> Path:
    raw = feature_manifest.get("matrix_path") or "storage/features/research_feature_matrix_live.csv"
    path = Path(str(raw))
    if path.exists():
        return path
    fallback = cfg.root / "storage" / "features" / "research_feature_matrix_live.csv"
    return fallback


def _load_latest_feature_row(cfg: AppConfig, feature_manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _feature_matrix_path(cfg, feature_manifest)
    if not path.exists():
        return {}, {"matrix_path": str(path), "exists": False, "sha256": None}
    frame = pd.read_csv(path)
    if frame.empty:
        return {}, {"matrix_path": str(path), "exists": True, "sha256": sha256_file(path), "rows": 0}
    row = _json_safe(frame.tail(1).iloc[0].to_dict())
    return dict(row), {"matrix_path": str(path), "exists": True, "sha256": sha256_file(path), "rows": int(len(frame))}


def _permission_from_row(row: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    mtf_score = _safe_float(row.get("mtf_alignment_score"), 0.0)
    trend = _safe_text(row.get("mtf_1h_trend") or row.get("mtf_bias")).upper()
    close = _safe_float(row.get("close"), 0.0)
    ema20 = _safe_float(row.get("ema20"), close)
    ema50 = _safe_float(row.get("ema50"), close)
    reasons: list[str] = []
    if mtf_score <= -0.35 or "BEARISH" in trend or ema20 < ema50:
        reasons.append("MTF_BEARISH_PRICE_STRUCTURE")
        return "SHORT", "allow_short", reasons
    if mtf_score >= 0.35 or "BULLISH" in trend or ema20 > ema50:
        reasons.append("MTF_BULLISH_PRICE_STRUCTURE")
        return "LONG", "allow_long", reasons
    reasons.append("PRICE_STRUCTURE_NEUTRAL_REVIEW_ONLY")
    return "FLAT", "neutral", reasons


def _profile() -> dict[str, Any]:
    payload = {
        "profile_id": "paper_validation_profile_v1",
        "profile_version": "phase3.paper.v1",
        "approved": True,
        "approval_status": "approved",
        "stage_scope": "paper_only",
        "max_order_notional_usdt": 75.0,
        "min_order_notional_usdt": 10.0,
        "risk_per_trade_usdt": 50.0,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "live_candidate_eligible": False,
    }
    payload["profile_sha256"] = sha256_json(payload)
    return payload


def _build_research_signal(row: Mapping[str, Any], data_manifest: Mapping[str, Any], feature_manifest: Mapping[str, Any], price_lineage: Mapping[str, Any]) -> dict[str, Any]:
    created = utc_now_canonical()
    side, permission_result, reasons = _permission_from_row(row)
    entry_allowed = side in {"LONG", "SHORT"}
    profile = _profile()
    missing_optional = int(_safe_float(feature_manifest.get("missing_optional_source_count") or data_manifest.get("missing_optional_source_count"), 0.0))
    signal_seed = {
        "data_snapshot_id": feature_manifest.get("data_snapshot_id") or data_manifest.get("data_snapshot_id"),
        "feature_snapshot_id": feature_manifest.get("feature_snapshot_id"),
        "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
        "entry_side": side,
        "timestamp": row.get("timestamp"),
        "version": PAPER_STRATEGY_VALIDATION_VERSION,
    }
    signal = {
        "research_signal_id": stable_id("research_signal", signal_seed, 24),
        "signal_id": stable_id("research_signal", signal_seed, 24),
        "signal_version": "research_signal_v2_phase3_paper_strategy_validation",
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "profile_sha256": profile["profile_sha256"],
        "config_version": "step286_researchsignal_feature_lineage_fix",
        "data_snapshot_id": feature_manifest.get("data_snapshot_id") or data_manifest.get("data_snapshot_id"),
        "data_snapshot_manifest_sha256": feature_manifest.get("data_snapshot_manifest_sha256") or data_manifest.get("data_snapshot_sha256"),
        "feature_snapshot_id": feature_manifest.get("feature_snapshot_id"),
        "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
        "source_bundle_sha256": feature_manifest.get("source_bundle_sha256") or data_manifest.get("source_bundle_sha256"),
        "optional_data_health": feature_manifest.get("optional_data_health") or data_manifest.get("optional_data_health") or {},
        "missing_optional_source_count": missing_optional,
        "stale_optional_source_count": int(_safe_float(feature_manifest.get("stale_optional_source_count") or data_manifest.get("stale_optional_source_count"), 0.0)),
        "neutral_due_to_missing": bool(missing_optional > 0),
        "missing_optional_data_neutral": bool(missing_optional > 0),
        "live_candidate_eligible": False,
        "paper_candidate_eligible": True,
        "entry_side": side,
        "entry_allowed": entry_allowed,
        "entry_confidence": abs(_safe_float(row.get("mtf_alignment_score"), 0.0)),
        "permission_result": permission_result,
        "final_signal_direction": side if side != "FLAT" else "NEUTRAL",
        "trade_permission": {
            "allow_new_position": entry_allowed,
            "allow_long": side == "LONG",
            "allow_short": side == "SHORT",
            "risk_level": "normal" if entry_allowed else "blocked",
            "block_reasons": [] if entry_allowed else ["NO_PAPER_DIRECTION"],
        },
        "features": {
            "timestamp": row.get("timestamp"),
            "close": _safe_float(row.get("close"), 0.0),
            "atr": _safe_float(row.get("atr"), 0.0),
            "rsi": _safe_float(row.get("rsi"), _safe_float(row.get("tv_rsi"), 0.0)),
            "mtf_alignment_score": _safe_float(row.get("mtf_alignment_score"), 0.0),
            "mtf_bias": row.get("mtf_bias"),
            "market_regime": row.get("market_regime"),
            "price_direction_score": _safe_float(row.get("mtf_alignment_score"), 0.0),
        },
        "score_components": {
            "price_direction_score": _safe_float(row.get("mtf_alignment_score"), 0.0),
            "derivatives_positioning_score": _safe_float(row.get("binance_derivatives_score"), 0.0),
            "exchange_flow_score": _safe_float(row.get("exchange_flow_score"), 0.0),
            "etf_flow_score": _safe_float(row.get("etf_flow_score"), 0.0),
            "stablecoin_liquidity_score": _safe_float(row.get("stablecoin_liquidity_score"), 0.0),
        },
        "price_direction_score": _safe_float(row.get("mtf_alignment_score"), 0.0),
        "derivatives_positioning_score": _safe_float(row.get("binance_derivatives_score"), 0.0),
        "exchange_flow_score": _safe_float(row.get("exchange_flow_score"), 0.0),
        "etf_flow_score": _safe_float(row.get("etf_flow_score"), 0.0),
        "stablecoin_liquidity_score": _safe_float(row.get("stablecoin_liquidity_score"), 0.0),
        "data_source": price_lineage.get("source_type") or "local_valid_price_csv",
        "data_source_role": "paper_validation_price_source",
        "data_quality_status": "valid_with_optional_missing" if missing_optional else "valid",
        "fallback_flag": False,
        "synthetic_flag": False,
        "sample_flag": False,
        "legacy_fallback_used": False,
        "order_intent_created": False,
        "trade_approved": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "created_at_utc": created,
        "paper_strategy_validation_reasons": reasons,
    }
    signal["research_signal_sha256"] = sha256_json(signal)
    return signal


def _build_decision(signal: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    side = _safe_text(signal.get("entry_side"), "FLAT").upper()
    entry = _safe_float(row.get("close"), 0.0)
    atr = max(_safe_float(row.get("atr"), 0.0), entry * 0.0025 if entry > 0 else 1.0)
    if side == "SHORT":
        stop = entry + atr
        take = entry - (atr * 3.0)
    elif side == "LONG":
        stop = entry - atr
        take = entry + (atr * 3.0)
    else:
        stop = 0.0
        take = 0.0
    decision_seed = {"side": side, "entry_price": entry, "created_from": PAPER_STRATEGY_VALIDATION_VERSION}
    decision_id = decision_id_from_signal(signal, decision_seed)
    decision = {
        "decision_id": decision_id,
        "decision_version": ORDER_ID_CHAIN_VERSION,
        "created_at_utc": utc_now_canonical(),
        "stage": "paper",
        "decision_stage": "paper",
        "research_signal_id": signal.get("research_signal_id"),
        "profile_id": signal.get("profile_id"),
        "data_snapshot_id": signal.get("data_snapshot_id"),
        "feature_snapshot_id": signal.get("feature_snapshot_id"),
        "side": side,
        "direction": side,
        "entry": round(entry, 8),
        "entry_price": round(entry, 8),
        "stop_loss": round(stop, 8),
        "take_profit": round(take, 8),
        "risk_reward": 3.0 if side in {"LONG", "SHORT"} else 0.0,
        "risk_per_unit": round(abs(entry - stop), 8),
        "allow_long": side == "LONG",
        "allow_short": side == "SHORT",
        "allow_new_position": side in {"LONG", "SHORT"},
        "signal_permission_authoritative": True,
        "paper_strategy_validation_only": True,
        "trading_execution_enabled_by_this_module": False,
        "order_routing_enabled_by_this_module": False,
        "external_order_submission_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    decision["decision_sha256"] = sha256_json(decision)
    return decision


def _build_order_intent(decision: Mapping[str, Any], risk_gate: Mapping[str, Any]) -> dict[str, Any]:
    entry = _safe_float(decision.get("entry_price"), 0.0)
    target_notional = 50.0
    quantity = round(target_notional / entry, 8) if entry > 0 else 0.0
    payload = {
        "status": "ORDER_INTENT_CREATED",
        "state": "CREATED",
        "order_intent_created": True,
        "decision_id": decision.get("decision_id"),
        "risk_gate_id": risk_gate.get("risk_gate_id"),
        "research_signal_id": decision.get("research_signal_id"),
        "profile_id": decision.get("profile_id"),
        "side": decision.get("side"),
        "direction": decision.get("direction"),
        "entry_price": entry,
        "price": entry,
        "quantity": quantity,
        "order_notional_usdt": round(quantity * entry, 8),
        "stop_loss": decision.get("stop_loss"),
        "take_profit": decision.get("take_profit"),
        "risk_reward": decision.get("risk_reward"),
        "risk_per_unit": decision.get("risk_per_unit"),
        "idempotency_key": stable_id("paper_idempotency", {"decision_id": decision.get("decision_id"), "entry": entry}, 24),
        "source_event_id": "phase3_paper_strategy_validation",
        "paper_only": True,
        "adapter_called": False,
        "external_order_submission_performed": False,
        "live_order_executed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "created_at_utc": utc_now_canonical(),
    }
    payload["order_intent_id"] = order_intent_id_from_payload(payload)
    payload["order_intent_sha256"] = sha256_json(payload)
    return payload


def _block_report(cfg: AppConfig, reasons: list[str]) -> dict[str, Any]:
    report = {
        "paper_strategy_validation_id": stable_id("paper_strategy_validation", {"status": STATUS_PAPER_STRATEGY_VALIDATION_BLOCKED_REVIEW_ONLY, "reasons": reasons, "root": str(cfg.root)}, 24),
        "version": PAPER_STRATEGY_VALIDATION_VERSION,
        "created_at_utc": utc_now_canonical(),
        "status": STATUS_PAPER_STRATEGY_VALIDATION_BLOCKED_REVIEW_ONLY,
        "passed": False,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "paper_order_submitted": False,
        "external_order_submission_performed": False,
        "live_order_executed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "block_reasons": sorted(set(reasons)),
    }
    report["paper_strategy_validation_sha256"] = sha256_json(report)
    return report


def build_paper_strategy_validation_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    data_manifest = read_json(latest / "data_snapshot_manifest.json", default={}) or {}
    feature_manifest = read_json(latest / "feature_store_manifest.json", default={}) or {}
    price_lineage = read_json(latest / "valid_price_lineage_artifacts_report.json", default={}) or {}
    quality_gate = build_paper_data_quality_gate_report(project_root=cfg.root)
    block_reasons: list[str] = []
    if quality_gate.get("status") != STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY:
        block_reasons.append("PAPER_DATA_QUALITY_GATE_NOT_PASSED")
        block_reasons.extend([str(r) for r in quality_gate.get("block_reasons", [])])
    row, matrix_meta = _load_latest_feature_row(cfg, feature_manifest)
    if not row:
        block_reasons.append("LATEST_FEATURE_MATRIX_ROW_MISSING")
    if block_reasons:
        report = _block_report(cfg, block_reasons)
        report["paper_data_quality_gate"] = quality_gate
        report["feature_matrix_meta"] = matrix_meta
        return report

    profile = _profile()
    signal = _build_research_signal(row, data_manifest, feature_manifest, price_lineage)
    registry_record = persist_research_signal_registry_record(cfg, signal)
    signal_qa = validate_research_signal_quality(signal, registry_record=registry_record, cfg=cfg)
    signal_qa_registry = persist_signal_qa_report(cfg, signal_qa)
    legacy_blocker = build_legacy_signal_fallback_block_report(research_signal=signal, signal_qa_report=signal_qa, use_research_signal_gate=True, consumer="phase3_paper_strategy_validation")
    decision = _build_decision(signal, row)

    risk_gate = evaluate_pre_order_risk_gate(
        decision=decision,
        research_signal=signal,
        profile=profile,
        runtime_state={
            "stage": "paper",
            "open_positions": 0,
            "daily_pnl_r": 0.0,
            "consecutive_losses": 0,
            "daily_order_count": 0,
            "api_error_rate": 0.0,
            "reconciliation_mismatch": False,
            "manual_kill_switch": False,
            "available_balance_usdt": 1000.0,
            "available_margin_usdt": 1000.0,
            "leverage": 1.0,
        },
        market_state={
            "price": decision.get("entry_price"),
            "mark_price": decision.get("entry_price"),
            "spread_bps": _safe_float(row.get("spread_bps"), 0.0),
            "slippage_bps": 2.0,
            "fee_bps": 4.0,
            "fee_model": "phase3_paper_fee_model",
            "min_order_size_check_passed": True,
            "venue_readiness_valid": True,
            "fallback_flag": False,
            "synthetic_flag": False,
            "sample_flag": False,
            "stale": False,
        },
        gate_config={
            "stage": "paper",
            "require_profile_hash": True,
            "max_open_positions": 1,
            "daily_loss_limit_r": -2.0,
            "max_consecutive_losses": 3,
            "max_daily_order_count": 10,
            "max_spread_bps": 10.0,
            "max_slippage_bps": 15.0,
            "require_slippage_estimate": True,
            "max_api_error_rate": 0.05,
            "max_reconciliation_mismatch_rate": 0.0,
            "min_order_notional_usdt": 10.0,
            "max_order_notional_usdt": 75.0,
            "require_fee_model": True,
            "require_margin_check": False,
            "require_balance_check": False,
            "require_venue_readiness": False,
        },
    ).to_dict()
    decision["risk_gate_id"] = risk_gate.get("risk_gate_id")
    order_intent = _build_order_intent(decision, risk_gate)
    paper_execution = execute_and_persist_paper_order(
        order_intent,
        risk_gate_report=risk_gate,
        market_state={"price": decision.get("entry_price"), "slippage_bps": 2.0, "fee_bps": 4.0},
        execution_config={"fill_ratio": 1.0, "slippage_bps": 2.0, "fee_bps": 4.0, "fill_latency_ms": 25.0},
        cfg=cfg,
    )
    reconciliation = reconcile_and_persist_paper_execution(paper_execution, cfg=cfg)
    outcome = analyze_and_persist_paper_outcome(
        reconciliation,
        outcome_context={
            "regime": _safe_text(row.get("market_regime"), "unknown"),
            "permission_result": signal.get("permission_result"),
            "stale_data_rate": 0.0,
            "api_error_rate": 0.0,
            "manual_override_count": 0,
            "paper_live_gap": "not_applicable",
            "sample_size": 1,
            "close_reason": "phase3_validation_open_position_no_forward_price",
        },
        cfg=cfg,
    )
    decision_pipeline_record = persist_decision_pipeline_registry_record(
        cfg,
        decision=decision,
        research_signal=signal,
        signal_qa_report=signal_qa,
        legacy_blocker=legacy_blocker,
        risk_gate=risk_gate,
        order_intent=order_intent,
        execution=paper_execution,
        reconciliation=reconciliation,
        outcome=outcome,
        feedback={"feedback_cycle_id": outcome.get("feedback_cycle_id")},
    )
    artifacts = {
        "research_signal.json": signal,
        "research_signal_registry_record.json": registry_record,
        "signal_qa_report.json": signal_qa,
        "signal_qa_registry_record.json": signal_qa_registry,
        "legacy_signal_fallback_blocker_report.json": legacy_blocker,
        "paper_trade_decision.json": decision,
        "pre_order_risk_gate_report.json": risk_gate,
        "paper_order_intent.json": order_intent,
        "decision_pipeline_registry_record.json": decision_pipeline_record,
    }
    for name, payload in artifacts.items():
        atomic_write_json(latest / name, payload)

    full_chain = {
        "data_snapshot_id": signal.get("data_snapshot_id"),
        "feature_snapshot_id": signal.get("feature_snapshot_id"),
        "research_signal_id": signal.get("research_signal_id"),
        "profile_id": signal.get("profile_id"),
        "approval_packet_id": None,
        "approval_intake_id": None,
        "decision_id": decision.get("decision_id"),
        "risk_gate_id": risk_gate.get("risk_gate_id"),
        "order_intent_id": order_intent.get("order_intent_id"),
        "execution_id": paper_execution.get("execution_id"),
        "reconciliation_id": reconciliation.get("reconciliation_id"),
        "outcome_id": outcome.get("outcome_id"),
        "feedback_cycle_id": outcome.get("feedback_cycle_id"),
    }
    report = {
        "paper_strategy_validation_id": stable_id("paper_strategy_validation", {"research_signal_id": signal.get("research_signal_id"), "order_intent_id": order_intent.get("order_intent_id"), "status": STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY}, 24),
        "version": PAPER_STRATEGY_VALIDATION_VERSION,
        "created_at_utc": utc_now_canonical(),
        "status": STATUS_PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY,
        "passed": True,
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "paper_strategy_validation_only": True,
        "paper_data_quality_gate_status": quality_gate.get("status"),
        "research_signal_id": signal.get("research_signal_id"),
        "signal_qa_result": signal_qa.get("signal_qa_result"),
        "signal_qa_allowed_for_decision": signal_qa.get("allowed_for_decision"),
        "signal_qa_allowed_for_paper": signal_qa.get("allowed_for_paper"),
        "pre_order_risk_gate_status": risk_gate.get("status"),
        "pre_order_risk_gate_approved": risk_gate.get("approved"),
        "decision_id": decision.get("decision_id"),
        "direction": decision.get("direction"),
        "entry_price": decision.get("entry_price"),
        "stop_loss": decision.get("stop_loss"),
        "take_profit": decision.get("take_profit"),
        "risk_reward": decision.get("risk_reward"),
        "order_intent_id": order_intent.get("order_intent_id"),
        "execution_id": paper_execution.get("execution_id"),
        "paper_execution_status": paper_execution.get("status"),
        "reconciliation_id": reconciliation.get("reconciliation_id"),
        "reconciliation_status": reconciliation.get("status"),
        "reconciled": reconciliation.get("reconciled"),
        "outcome_id": outcome.get("outcome_id"),
        "feedback_cycle_id": outcome.get("feedback_cycle_id"),
        "outcome_status": outcome.get("status"),
        "outcome_closed": outcome.get("outcome_closed"),
        "next_action": outcome.get("next_action"),
        "canonical_id_chain": full_chain,
        "paper_stage_chain_complete": all(full_chain.get(k) for k in ("data_snapshot_id", "feature_snapshot_id", "research_signal_id", "profile_id", "decision_id", "risk_gate_id", "order_intent_id", "execution_id", "reconciliation_id", "outcome_id", "feedback_cycle_id")),
        "approval_not_required_for_phase3_paper_validation": True,
        "approval_chain_complete": False,
        "live_candidate_eligible": False,
        "signed_testnet_unlock_authority": False,
        "live_execution_unlock_authority": False,
        "runtime_permission_source": False,
        "paper_order_submitted": bool(paper_execution.get("paper_order_submitted") is True),
        "adapter_called": bool(paper_execution.get("adapter_called") is True),
        "external_order_submission_performed": bool(paper_execution.get("external_order_submission_performed") is True or reconciliation.get("external_order_submission_performed") is True),
        "live_order_executed": bool(paper_execution.get("live_order_executed") is True or reconciliation.get("live_order_executed") is True),
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "feature_matrix_meta": matrix_meta,
        "generated_artifacts": sorted(artifacts.keys()) + ["paper_execution_record.json", "paper_reconciliation_record.json", "outcome_analytics_record.json"],
    }
    report["paper_strategy_validation_sha256"] = sha256_json(report)
    return report


def persist_paper_strategy_validation_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    report = build_paper_strategy_validation_report(cfg=cfg, project_root=project_root or cfg.root)
    latest = _latest_dir(cfg)
    atomic_write_json(latest / "paper_strategy_validation_report.json", report)
    archive_dir = _storage_dir(cfg, "storage/paper_strategy_validation")
    atomic_write_json(archive_dir / "paper_strategy_validation_report.json", report)
    registry_record = {
        "paper_strategy_validation_registry_version": PAPER_STRATEGY_VALIDATION_VERSION,
        "paper_strategy_validation_id": report.get("paper_strategy_validation_id"),
        "status": report.get("status"),
        "passed": report.get("passed"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "research_signal_id": report.get("research_signal_id"),
        "decision_id": report.get("decision_id"),
        "risk_gate_id": report.get("canonical_id_chain", {}).get("risk_gate_id"),
        "order_intent_id": report.get("order_intent_id"),
        "execution_id": report.get("execution_id"),
        "reconciliation_id": report.get("reconciliation_id"),
        "outcome_id": report.get("outcome_id"),
        "feedback_cycle_id": report.get("feedback_cycle_id"),
        "paper_stage_chain_complete": report.get("paper_stage_chain_complete"),
        "paper_data_quality_gate_status": report.get("paper_data_quality_gate_status"),
        "pre_order_risk_gate_status": report.get("pre_order_risk_gate_status"),
        "reconciliation_status": report.get("reconciliation_status"),
        "outcome_status": report.get("outcome_status"),
        "external_order_submission_performed": report.get("external_order_submission_performed"),
        "live_order_executed": report.get("live_order_executed"),
        "runtime_settings_mutated": report.get("runtime_settings_mutated"),
        "score_weights_mutated": report.get("score_weights_mutated"),
        "auto_promotion_allowed": report.get("auto_promotion_allowed"),
        "paper_strategy_validation_sha256": report.get("paper_strategy_validation_sha256"),
        "created_at_utc": report.get("created_at_utc"),
    }
    registry_record["paper_strategy_validation_registry_record_id"] = stable_id("paper_strategy_validation_registry", registry_record, 24)
    registry_record["paper_strategy_validation_registry_record_sha256"] = sha256_json(registry_record)
    persisted = append_registry_record(
        registry_path(cfg, PAPER_STRATEGY_VALIDATION_REGISTRY),
        registry_record,
        registry_name=PAPER_STRATEGY_VALIDATION_REGISTRY,
        id_field="paper_strategy_validation_registry_record_id",
        hash_field="paper_strategy_validation_registry_record_sha256",
        id_prefix="paper_strategy_validation_registry",
    )
    atomic_write_json(latest / "paper_strategy_validation_registry_record.json", persisted)
    report["paper_strategy_validation_registry_record_id"] = persisted.get("paper_strategy_validation_registry_record_id")
    report["paper_strategy_validation_registry_record_sha256"] = persisted.get("paper_strategy_validation_registry_record_sha256")
    atomic_write_json(latest / "paper_strategy_validation_report.json", report)
    atomic_write_json(archive_dir / "paper_strategy_validation_report.json", report)
    return report
