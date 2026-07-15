"""Phase S5: ChampionSelectionAgent — one champion per generation batch.

Two gates, both required (directive §6.7): a strategy must clear the *absolute*
performance gate (already decided by the BacktestAgent's ``qualified`` flag) and
then win the *relative* ranking among the batch's qualified strategies. A batch
can produce no champion at all — being the best of four losers is not a pass.

The relative score follows §17: a weighted blend of expectancy, profit factor,
walk-forward stability, regime consistency, and sample quality, minus a drawdown
penalty. Expectancy, profit factor, and drawdown are min-max normalised *within
the batch* (relative ranking); stability, regime consistency, and sample quality
are already absolute 0..1 signals. Win rate is deliberately not in the score — it
is a supporting indicator only.

Selecting a champion grants nothing at runtime. The record's permission flags say
a champion may later be *added to the paper pool* (S6) — testnet/live remain
manual. This agent submits no orders and mutates no settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from crypto_ai_system.utils.audit import stable_id, utc_now_canonical


@dataclass(frozen=True)
class ChampionScoreWeights:
    expectancy: float = 0.30
    profit_factor: float = 0.20
    walk_forward_stability: float = 0.20
    regime_consistency: float = 0.10
    sample_quality: float = 0.10
    drawdown_penalty: float = 0.10
    sample_target: int = 100  # trade count for full sample-quality credit


def _coalesce(value: Any, default: float = 0.0) -> float:
    return default if value is None else float(value)


def _normalize(values: list[float]) -> list[float]:
    """Min-max to [0, 1]. A flat set (all equal) scores 1.0 — everyone is tied top."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    span = hi - lo
    return [(v - lo) / span for v in values]


def _candidate_metrics(record: dict) -> dict[str, float]:
    metrics = record.get("metrics") or {}
    wf = record.get("walk_forward") or {}
    return {
        "expectancy_r": _coalesce(metrics.get("expectancy_r")),
        "profit_factor": _coalesce(metrics.get("profit_factor")),
        "max_drawdown_r": _coalesce(metrics.get("max_drawdown_r")),
        "trade_count": _coalesce(metrics.get("trade_count")),
        "regime_consistency": _coalesce(metrics.get("regime_consistency")),
        "temporal_stability": _coalesce(wf.get("temporal_stability")),
        "win_rate": _coalesce(metrics.get("win_rate")),
    }


def _score_candidates(records: Sequence[dict], weights: ChampionScoreWeights) -> list[dict[str, Any]]:
    metrics = [_candidate_metrics(r) for r in records]

    norm_expectancy = _normalize([m["expectancy_r"] for m in metrics])
    norm_profit_factor = _normalize([m["profit_factor"] for m in metrics])
    # Higher drawdown -> higher penalty, so normalise the drawdowns directly.
    norm_drawdown = _normalize([m["max_drawdown_r"] for m in metrics])

    scored: list[dict[str, Any]] = []
    for record, m, ne, npf, ndd in zip(records, metrics, norm_expectancy, norm_profit_factor, norm_drawdown):
        sample_quality = min(m["trade_count"] / weights.sample_target, 1.0) if weights.sample_target else 0.0
        components = {
            "expectancy": weights.expectancy * ne,
            "profit_factor": weights.profit_factor * npf,
            "walk_forward_stability": weights.walk_forward_stability * m["temporal_stability"],
            "regime_consistency": weights.regime_consistency * m["regime_consistency"],
            "sample_quality": weights.sample_quality * sample_quality,
            "drawdown_penalty": -weights.drawdown_penalty * ndd,
        }
        scored.append({
            "strategy_id": record.get("strategy_id"),
            "strategy_rule_hash": record.get("strategy_rule_hash"),
            "champion_score": round(sum(components.values()), 8),
            "score_components": {k: round(v, 8) for k, v in components.items()},
            "expectancy_r": m["expectancy_r"],
            "max_drawdown_r": m["max_drawdown_r"],
            "win_rate": m["win_rate"],
        })
    return scored


def select_batch_champion(
    records: Sequence[dict[str, Any]],
    *,
    generation_id: str | None = None,
    weights: ChampionScoreWeights | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Choose at most one champion from a batch's backtest records."""
    weights = weights or ChampionScoreWeights()
    gen_id = generation_id
    if gen_id is None and records:
        gen_id = records[0].get("generation_id")

    qualified = [r for r in records if r.get("qualified") is True]

    result: dict[str, Any] = {
        "generation_id": gen_id,
        "candidates_considered": len(records),
        "qualified_count": len(qualified),
        "can_add_to_paper_pool": True,
        "can_add_to_testnet_pool": False,
        "can_add_to_live_pool": False,
    }

    if not qualified:
        result.update({
            "selection_status": "NO_CHAMPION",
            "selected_strategy_id": None,
            "activation_permission": None,
            "champion_score": None,
            "ranked": [],
        })
        result["champion_selection_id"] = stable_id("champion_selection", result, 24)
        result["created_at_utc"] = now or utc_now_canonical()
        return result

    scored = _score_candidates(qualified, weights)
    # Deterministic ordering: score, then expectancy, then lower drawdown, then id.
    ranked = sorted(
        scored,
        key=lambda s: (s["champion_score"], s["expectancy_r"], -s["max_drawdown_r"], s["strategy_id"] or ""),
        reverse=True,
    )
    winner = ranked[0]

    result.update({
        "selection_status": "BATCH_CHAMPION",
        "selected_strategy_id": winner["strategy_id"],
        "selected_strategy_rule_hash": winner["strategy_rule_hash"],
        "activation_permission": "PAPER_ONLY",
        "champion_score": winner["champion_score"],
        "ranked": ranked,
    })
    result["champion_selection_id"] = stable_id("champion_selection", result, 24)
    result["created_at_utc"] = now or utc_now_canonical()
    return result
