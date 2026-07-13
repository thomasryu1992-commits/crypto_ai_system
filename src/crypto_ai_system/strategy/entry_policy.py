from __future__ import annotations

import pandas as pd

from crypto_ai_system.config import AppConfig


def _mode_threshold(mode: str, base: float) -> float:
    mode = str(mode or 'normal').lower()
    if mode == 'off':
        return 999.0
    if mode == 'strict':
        return base * 0.5
    return base


def generate_signal(row: pd.Series, cfg: AppConfig) -> str:
    if row.get('data_quality_status') == 'WARMUP':
        return 'FLAT'

    regime = row.get('market_regime', 'UNCLEAR')
    score = float(row.get('research_score', 0) or 0)
    close = row.get('close')
    ma20 = row.get('ma20')
    ma50 = row.get('ma50')
    adx = float(row.get('adx', 0) or 0)
    rsi = float(row.get('rsi', 50) or 50)
    funding = abs(float(row.get('funding_rate', 0) or 0))
    oi_chg_abs = abs(float(row.get('oi_change_pct', 0) or 0))
    spread_bps = float(row.get('spread_bps', 0) or 0)

    bullish_threshold = float(cfg.get('entry_policy.bullish_threshold', 0.58))
    bearish_threshold = float(cfg.get('entry_policy.bearish_threshold', -0.58))
    adx_threshold = float(cfg.get('entry_policy.adx_trend_threshold', 20))
    funding_abs_block = _mode_threshold(cfg.get('entry_policy.funding_filter_mode', 'normal'), float(cfg.get('entry_policy.funding_abs_block', 0.0008)))
    oi_change_abs_block = _mode_threshold(cfg.get('entry_policy.oi_filter_mode', 'normal'), float(cfg.get('entry_policy.oi_change_abs_block', 0.08)))
    spread_block = float(cfg.get('entry_policy.spread_bps_block', 10))
    allow_trend = bool(cfg.get('entry_policy.allow_trend_entry', True))
    allow_range = bool(cfg.get('entry_policy.allow_range_entry', True))
    allow_liq = bool(cfg.get('entry_policy.allow_liquidation_reversal', False))

    if funding > funding_abs_block or oi_chg_abs > oi_change_abs_block:
        return 'FLAT'
    if spread_block > 0 and spread_bps > spread_block:
        return 'FLAT'

    if allow_trend and regime == 'TREND_UP' and score >= bullish_threshold:
        if close > ma20 > ma50 and adx >= adx_threshold:
            return 'LONG'

    if allow_trend and regime == 'TREND_DOWN' and score <= bearish_threshold:
        if close < ma20 < ma50 and adx >= adx_threshold:
            return 'SHORT'

    if allow_range and regime == 'RANGE':
        if rsi <= float(cfg.get('entry_policy.rsi_range_long', 35)) and score > -0.2:
            return 'LONG'
        if rsi >= float(cfg.get('entry_policy.rsi_range_short', 65)) and score < 0.2:
            return 'SHORT'

    if allow_liq:
        if int(row.get('long_liquidation_spike', 0)) == 1 and score > 0 and regime != 'TREND_DOWN':
            return 'LONG'
        if int(row.get('short_liquidation_spike', 0)) == 1 and score < 0 and regime != 'TREND_UP':
            return 'SHORT'

    return 'FLAT'


def attach_signals(features: pd.DataFrame, cfg: AppConfig) -> pd.DataFrame:
    df = features.copy()
    df['signal'] = df.apply(lambda row: generate_signal(row, cfg), axis=1)
    return df
