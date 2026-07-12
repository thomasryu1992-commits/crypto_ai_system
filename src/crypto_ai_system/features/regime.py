from __future__ import annotations

import pandas as pd


def classify_market_regime(row: pd.Series, adx_threshold: float = 20.0) -> str:
    close = row.get('close')
    ma20 = row.get('ma20')
    ma50 = row.get('ma50')
    adx = row.get('adx')
    atr_pct = row.get('atr_percentile')

    if pd.isna(close) or pd.isna(ma20) or pd.isna(ma50) or pd.isna(adx):
        return 'UNCLEAR'

    if not pd.isna(atr_pct):
        if atr_pct >= 0.80:
            return 'HIGH_VOLATILITY'
        if atr_pct <= 0.20 and adx < adx_threshold:
            return 'LOW_VOLATILITY'

    if close > ma20 > ma50 and adx >= adx_threshold:
        return 'TREND_UP'
    if close < ma20 < ma50 and adx >= adx_threshold:
        return 'TREND_DOWN'
    if adx < adx_threshold:
        return 'RANGE'
    return 'UNCLEAR'
