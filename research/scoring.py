from __future__ import annotations


def score_market_context(context: dict) -> dict:
    snapshot = context.get("snapshot", {})
    positives = context.get("positives", [])
    risks = context.get("risks", [])

    market_structure_score = 50
    momentum_score = 50
    derivatives_score = 50
    data_quality_penalty = 0

    trend = snapshot.get("trend_bias")
    if trend == "bullish":
        market_structure_score += 20
    elif trend == "bearish":
        market_structure_score -= 20

    change_24h = float(snapshot.get("change_24h_pct", 0))
    if change_24h > 1:
        momentum_score += 15
    elif change_24h < -1:
        momentum_score -= 15

    volume_ratio = float(snapshot.get("volume_ratio", 1))
    if volume_ratio > 1.2:
        momentum_score += 5

    funding = float(snapshot.get("funding_rate", 0))
    oi_change = float(snapshot.get("open_interest_change_24h", 0))
    if abs(funding) > 0.001:
        derivatives_score -= 10
    if oi_change > 0 and change_24h > 0:
        derivatives_score += 5
    if oi_change > 0 and change_24h < 0:
        derivatives_score -= 5

    if snapshot.get("is_synthetic") or snapshot.get("is_fallback"):
        data_quality_penalty = 20

    final_score = (
        market_structure_score * 0.35
        + momentum_score * 0.25
        + derivatives_score * 0.25
        + 50 * 0.15
        - data_quality_penalty
    )
    final_score = max(0, min(100, round(final_score, 2)))

    return {
        "final_score": final_score,
        "market_structure_score": market_structure_score,
        "momentum_score": momentum_score,
        "derivatives_score": derivatives_score,
        "data_quality_penalty": data_quality_penalty,
        "positives": positives,
        "risks": risks,
    }
