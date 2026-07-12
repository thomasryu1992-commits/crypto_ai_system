from __future__ import annotations

import numpy as np
import pandas as pd


def compute_research_score(row: pd.Series) -> float:
    """Explainable derivatives-aware score for Extended Perp validation.

    Positive = bullish, Negative = bearish. This is intentionally transparent
    and sweep-friendly, not an opaque ML model.
    """
    score = 0.0

    close = row.get('close', np.nan)
    ma20 = row.get('ma20', np.nan)
    ma50 = row.get('ma50', np.nan)
    rsi = row.get('rsi', np.nan)
    adx = row.get('adx', np.nan)
    oi_chg = row.get('oi_change_pct', 0) or 0
    funding = row.get('funding_rate', 0) or 0
    basis = row.get('mark_index_basis_bps', 0) or 0
    regime = row.get('market_regime', 'UNCLEAR')

    if not pd.isna(close) and not pd.isna(ma20) and not pd.isna(ma50):
        if close > ma20 > ma50:
            score += 0.35
        elif close < ma20 < ma50:
            score -= 0.35

    if not pd.isna(rsi):
        if 45 <= rsi <= 65:
            score += 0.05
        elif rsi < 30:
            score += 0.15
        elif rsi > 70:
            score -= 0.15

    if not pd.isna(adx) and adx >= 20:
        if regime == 'TREND_UP':
            score += 0.20
        elif regime == 'TREND_DOWN':
            score -= 0.20

    if regime == 'TREND_UP' and oi_chg > 0:
        score += 0.10
    elif regime == 'TREND_DOWN' and oi_chg > 0:
        score -= 0.10

    # Extreme funding and mark/index basis are crowding risks.
    if funding > 0.0005:
        score -= 0.10
    elif funding < -0.0005:
        score += 0.10

    if basis > 15:
        score -= 0.05
    elif basis < -15:
        score += 0.05

    if int(row.get('long_liquidation_spike', 0)) == 1 and regime != 'TREND_DOWN':
        score += 0.05
    if int(row.get('short_liquidation_spike', 0)) == 1 and regime != 'TREND_UP':
        score -= 0.05

    return float(max(-1.0, min(1.0, score)))


def attach_research_scores(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    df['research_score'] = df.apply(compute_research_score, axis=1)
    return df
