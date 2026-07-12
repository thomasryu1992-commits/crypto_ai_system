from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Mapping

import pandas as pd

from crypto_ai_system.analysis.score_engine import ScoreEngine
from crypto_ai_system.analysis.market_condition import classify_market_condition
from crypto_ai_system.analysis.weights import DEFAULT_SCORE_WEIGHTS
from crypto_ai_system.research.research_signal_builder import build_research_signal
from crypto_ai_system.trading.permission_gate import evaluate_trade_permission


STEP259_CALIBRATION_VERSION = "step259_researchsignal_weight_calibration_v1"

# Candidate profiles are intentionally conservative. They do not auto-select a
# production winner; they make replay/backtest comparison reproducible.
DEFAULT_STEP259_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "baseline_step258": {
        "structure": 0.20,
        "momentum": 0.10,
        "derivatives": 0.25,
        "exchange_flow": 0.15,
        "etf_flow": 0.15,
        "stablecoin_liquidity": 0.10,
        "risk": 0.05,
        "onchain": 0.00,
    },
    "price_structure_dominant": {
        "structure": 0.35,
        "momentum": 0.15,
        "derivatives": 0.20,
        "exchange_flow": 0.10,
        "etf_flow": 0.10,
        "stablecoin_liquidity": 0.05,
        "risk": 0.05,
        "onchain": 0.00,
    },
    "flow_confirmed": {
        "structure": 0.18,
        "momentum": 0.08,
        "derivatives": 0.18,
        "exchange_flow": 0.22,
        "etf_flow": 0.20,
        "stablecoin_liquidity": 0.09,
        "risk": 0.05,
        "onchain": 0.00,
    },
    "liquidity_risk_guarded": {
        "structure": 0.18,
        "momentum": 0.08,
        "derivatives": 0.18,
        "exchange_flow": 0.16,
        "etf_flow": 0.16,
        "stablecoin_liquidity": 0.14,
        "risk": 0.10,
        "onchain": 0.00,
    },
}

_SCORE_COLUMNS = {
    "score_structure",
    "score_momentum",
    "score_derivatives",
    "score_exchange_flow",
    "score_etf_flow",
    "score_stablecoin_liquidity",
    "score_risk",
    "score_onchain",
    "score_total_score",
    "score_bias",
}


def normalize_score_weights(weights: Mapping[str, Any] | None) -> dict[str, float]:
    merged = dict(DEFAULT_SCORE_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key in merged:
                try:
                    merged[key] = max(0.0, float(value))
                except Exception:
                    merged[key] = 0.0
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_SCORE_WEIGHTS)
    return {key: round(value / total, 10) for key, value in merged.items()}


def resolve_weight_profiles(cfg: Any = None, profiles: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, dict[str, float]]:
    if profiles:
        raw_profiles = {str(name): dict(value) for name, value in profiles.items()}
    else:
        raw_profiles = dict(DEFAULT_STEP259_WEIGHT_PROFILES)
        getter = getattr(cfg, "get", None)
        configured = getter("research.score_weight_profiles", None) if callable(getter) else None
        if isinstance(configured, dict):
            for name, value in configured.items():
                if isinstance(value, dict):
                    raw_profiles[str(name)] = dict(value)
    return {name: normalize_score_weights(weights) for name, weights in raw_profiles.items()}


def _cfg_with_weights(cfg: Any, weights: Mapping[str, float]) -> Any:
    """Return a lightweight cfg copy with research.score_weights overridden."""
    settings = deepcopy(getattr(cfg, "settings", {}) or {})
    research = settings.setdefault("research", {})
    research["score_weights"] = dict(weights)

    class _CalibrationConfig:
        def __init__(self, root: Any, settings: dict[str, Any]):
            self.root = root
            self.settings = settings

        def get(self, path: str, default: Any = None) -> Any:
            node: Any = self.settings
            for part in str(path).split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return node

    return _CalibrationConfig(getattr(cfg, "root", None), settings)


def _base_feature_frame(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix is None or matrix.empty:
        return pd.DataFrame()
    out = matrix.copy().reset_index(drop=True)
    drop_cols = [col for col in out.columns if col in _SCORE_COLUMNS or col.startswith("score_")]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    return out


def _row_signal(row: pd.Series, cfg: Any, *, source: str | None = None) -> dict[str, Any]:
    snapshot = row.replace({pd.NA: None}).to_dict()
    condition = classify_market_condition(snapshot).to_dict()
    snapshot.update({
        "market_condition": condition.get("final_condition"),
        "volatility_state": condition.get("volatility_state"),
        "derivatives_state": condition.get("derivatives_state"),
        "liquidity_state": condition.get("liquidity_state"),
    })
    return build_research_signal(snapshot, condition, cfg, source=source or snapshot.get("data_source") or snapshot.get("source"))


def evaluate_weight_profile_on_matrix(
    matrix: pd.DataFrame,
    cfg: Any,
    weights: Mapping[str, float],
    *,
    profile_name: str = "custom",
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Replay a feature matrix under one score-weight profile.

    This is score/permission calibration only. It does not submit orders and does
    not imply a production profile selection.
    """
    base = _base_feature_frame(matrix)
    if base.empty:
        return {
            "profile_name": profile_name,
            "weights": normalize_score_weights(weights),
            "rows": 0,
            "status": "EMPTY_MATRIX",
            "permission_distribution": {"normal": 0, "reduced": 0, "blocked": 0},
            "side_distribution": {"LONG": 0, "SHORT": 0, "FLAT": 0},
            "entry_allowed_count": 0,
            "entry_allowed_ratio": 0.0,
            "blocked_ratio": 0.0,
            "reduced_ratio": 0.0,
            "average_score_total": 0.0,
            "block_reason_counts": {},
            "risk_warning_counts": {},
        }

    if max_rows is not None and max_rows > 0 and len(base) > max_rows:
        base = base.tail(max_rows).reset_index(drop=True)

    normalized = normalize_score_weights(weights)
    scored = ScoreEngine(normalized).score_frame(base)
    replay_cfg = _cfg_with_weights(cfg, normalized)

    risk_counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    block_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    allowed = 0
    score_total_sum = 0.0

    for _, row in scored.iterrows():
        signal = _row_signal(row, replay_cfg)
        decision = evaluate_trade_permission(signal, cfg=replay_cfg)
        risk_counts[decision.risk_level] += 1
        side_counts[decision.side] += 1
        if decision.entry_allowed:
            allowed += 1
        for reason in decision.block_reasons:
            block_counts[str(reason)] += 1
        for warning in decision.risk_warnings:
            warning_counts[str(warning)] += 1
        try:
            score_total_sum += float(row.get("score_total_score") or 0.0)
        except Exception:
            pass

    rows = int(len(scored))
    return {
        "profile_name": profile_name,
        "weights": normalized,
        "rows": rows,
        "status": "OK",
        "permission_distribution": {
            "normal": int(risk_counts.get("normal", 0)),
            "reduced": int(risk_counts.get("reduced", 0)),
            "blocked": int(risk_counts.get("blocked", 0)),
        },
        "side_distribution": {
            "LONG": int(side_counts.get("LONG", 0)),
            "SHORT": int(side_counts.get("SHORT", 0)),
            "FLAT": int(side_counts.get("FLAT", 0)),
        },
        "entry_allowed_count": int(allowed),
        "entry_allowed_ratio": round(allowed / rows, 6) if rows else 0.0,
        "blocked_ratio": round(risk_counts.get("blocked", 0) / rows, 6) if rows else 0.0,
        "reduced_ratio": round(risk_counts.get("reduced", 0) / rows, 6) if rows else 0.0,
        "average_score_total": round(score_total_sum / rows, 6) if rows else 0.0,
        "block_reason_counts": dict(sorted(block_counts.items())),
        "risk_warning_counts": dict(sorted(warning_counts.items())),
    }


def compare_weight_profiles(
    matrix: pd.DataFrame,
    cfg: Any,
    profiles: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    max_rows: int | None = None,
) -> dict[str, Any]:
    resolved = resolve_weight_profiles(cfg, profiles)
    results = [
        evaluate_weight_profile_on_matrix(matrix, cfg, weights, profile_name=name, max_rows=max_rows)
        for name, weights in resolved.items()
    ]
    return {
        "version": STEP259_CALIBRATION_VERSION,
        "profiles_compared": len(results),
        "rows_evaluated": max((item.get("rows", 0) for item in results), default=0),
        "results": results,
        "status": "OK" if results else "NO_PROFILES",
        "live_trading_allowed": False,
        "external_order_submission_performed": False,
    }


STEP260_CALIBRATION_REVIEW_VERSION = "step260_researchsignal_profile_review_only_calibration_v1"

DEFAULT_STEP260_ACCEPTANCE_CRITERIA: dict[str, float | int] = {
    "min_rows": 24,
    "min_entry_allowed_ratio": 0.03,
    "max_entry_allowed_ratio": 0.80,
    "max_blocked_ratio": 0.70,
    "max_reduced_ratio": 0.60,
    "target_entry_allowed_ratio": 0.25,
    "target_blocked_ratio": 0.35,
}

_PRODUCTION_MATRIX_SOURCE_TYPES = {"stored_feature_store_matrix", "explicit_feature_store_matrix"}


def resolve_step260_acceptance_criteria(cfg: Any = None, overrides: Mapping[str, Any] | None = None) -> dict[str, float | int]:
    """Resolve review-only profile acceptance thresholds.

    These thresholds only rank candidate score-weight profiles. They never mutate
    runtime config and never enable live/testnet order routing.
    """
    criteria: dict[str, float | int] = dict(DEFAULT_STEP260_ACCEPTANCE_CRITERIA)
    getter = getattr(cfg, "get", None)
    configured = getter("research.calibration_review", None) if callable(getter) else None
    if isinstance(configured, Mapping):
        for key in criteria:
            if key in configured:
                try:
                    value = configured[key]
                    criteria[key] = int(value) if key == "min_rows" else float(value)
                except Exception:
                    pass
    if overrides:
        for key in criteria:
            if key in overrides:
                try:
                    value = overrides[key]
                    criteria[key] = int(value) if key == "min_rows" else float(value)
                except Exception:
                    pass
    return criteria


def evaluate_profile_acceptance(
    profile_result: Mapping[str, Any],
    criteria: Mapping[str, Any] | None = None,
    *,
    matrix_source_type: str = "unknown",
) -> dict[str, Any]:
    """Evaluate one profile's permission distribution against review thresholds."""
    c = dict(DEFAULT_STEP260_ACCEPTANCE_CRITERIA)
    if criteria:
        c.update(criteria)

    rows = int(profile_result.get("rows") or 0)
    entry_allowed_ratio = float(profile_result.get("entry_allowed_ratio") or 0.0)
    blocked_ratio = float(profile_result.get("blocked_ratio") or 0.0)
    reduced_ratio = float(profile_result.get("reduced_ratio") or 0.0)

    failures: list[str] = []
    warnings: list[str] = []

    if matrix_source_type not in _PRODUCTION_MATRIX_SOURCE_TYPES:
        failures.append("NO_REAL_FEATURE_STORE_MATRIX")
    if rows < int(c["min_rows"]):
        failures.append("INSUFFICIENT_ROWS")
    if entry_allowed_ratio < float(c["min_entry_allowed_ratio"]):
        failures.append("ENTRY_ALLOWED_RATIO_TOO_LOW")
    if entry_allowed_ratio > float(c["max_entry_allowed_ratio"]):
        failures.append("ENTRY_ALLOWED_RATIO_TOO_HIGH")
    if blocked_ratio > float(c["max_blocked_ratio"]):
        failures.append("BLOCKED_RATIO_TOO_HIGH")
    if reduced_ratio > float(c["max_reduced_ratio"]):
        warnings.append("REDUCED_RATIO_HIGH")

    target_entry = float(c["target_entry_allowed_ratio"])
    target_blocked = float(c["target_blocked_ratio"])
    distribution_fit = 1.0
    distribution_fit -= min(1.0, abs(entry_allowed_ratio - target_entry)) * 0.60
    distribution_fit -= min(1.0, abs(blocked_ratio - target_blocked)) * 0.40
    distribution_fit = round(max(0.0, min(1.0, distribution_fit)), 6)

    status = "eligible_review_candidate" if not failures else "not_eligible"
    if warnings and status == "eligible_review_candidate":
        status = "eligible_with_warnings"

    return {
        "profile_name": str(profile_result.get("profile_name") or "unknown"),
        "status": status,
        "review_score": distribution_fit,
        "rows": rows,
        "entry_allowed_ratio": entry_allowed_ratio,
        "blocked_ratio": blocked_ratio,
        "reduced_ratio": reduced_ratio,
        "failures": failures,
        "warnings": warnings,
        "review_only": True,
    }


def rank_profile_candidates(
    comparison: Mapping[str, Any],
    criteria: Mapping[str, Any] | None = None,
    *,
    matrix_source_type: str = "unknown",
) -> dict[str, Any]:
    """Rank profile candidates without applying any winner to runtime settings."""
    reviewed = [
        evaluate_profile_acceptance(item, criteria, matrix_source_type=matrix_source_type)
        for item in comparison.get("results", [])
    ]
    eligible = [item for item in reviewed if item["status"] in {"eligible_review_candidate", "eligible_with_warnings"}]
    eligible_sorted = sorted(
        eligible,
        key=lambda item: (
            item["review_score"],
            -item["blocked_ratio"],
            item["entry_allowed_ratio"],
            item["profile_name"],
        ),
        reverse=True,
    )
    candidate = eligible_sorted[0]["profile_name"] if eligible_sorted else None
    reason = "candidate_ranked_for_manual_review" if candidate else "no_profile_met_review_thresholds"
    if matrix_source_type not in _PRODUCTION_MATRIX_SOURCE_TYPES:
        reason = "real_feature_store_matrix_required_before_candidate_selection"
        candidate = None

    return {
        "status": "review_only_completed" if reviewed else "no_profiles_to_review",
        "production_candidate_profile": candidate,
        "selection_reason": reason,
        "profile_reviews": reviewed,
        "auto_apply_selected_profile": False,
        "selected_profile_written_to_settings": False,
        "runtime_score_weights_mutated": False,
        "live_trading_allowed": False,
        "external_order_submission_performed": False,
    }


def build_step260_profile_review(
    matrix: pd.DataFrame,
    cfg: Any,
    *,
    matrix_source: str,
    matrix_source_type: str,
    profiles: Mapping[str, Mapping[str, Any]] | None = None,
    max_rows: int | None = None,
    criteria_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Step260 review-only calibration from a Feature Store matrix."""
    comparison = compare_weight_profiles(matrix, cfg, profiles=profiles, max_rows=max_rows)
    criteria = resolve_step260_acceptance_criteria(cfg, criteria_overrides)
    candidate_review = rank_profile_candidates(comparison, criteria, matrix_source_type=matrix_source_type)
    return {
        "version": STEP260_CALIBRATION_REVIEW_VERSION,
        "mode": "review_only",
        "matrix_source": matrix_source,
        "matrix_source_type": matrix_source_type,
        "matrix_rows_available": int(len(matrix)) if matrix is not None else 0,
        "rows_evaluated": int(comparison.get("rows_evaluated") or 0),
        "criteria": criteria,
        "comparison": comparison,
        "candidate_review": candidate_review,
        "production_profile_auto_applied": False,
        "config_mutated": False,
        "safety_boundaries": {
            "live_trading_allowed": False,
            "order_routing_enabled": False,
            "external_order_submission_performed": False,
            "canonical_live_execution_port_performed": False,
            "canonical_testnet_execution_port_performed": False,
            "root_package_deletion_performed": False,
            "root_package_deletion_deferred": True,
            "missing_canonical_module_count": 2,
        },
    }
