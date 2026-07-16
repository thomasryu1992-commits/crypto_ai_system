from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.features.higher_timeframe import add_higher_timeframe_features
from crypto_ai_system.features.indicators import (
    adx,
    atr,
    bollinger,
    ema,
    macd,
    roc,
    rolling_percentile,
    rsi,
    sma,
    zscore,
)
from crypto_ai_system.features.regime import classify_market_regime
from crypto_ai_system.data.price_data_loader import build_multi_timeframe_context
from crypto_ai_system.features.additional_data_features import build_additional_feature_snapshot


def _merge_close_feature(df: pd.DataFrame, other: pd.DataFrame | None, name: str) -> pd.DataFrame:
    if other is None or other.empty or 'close' not in other.columns:
        df[name] = np.nan
        return df
    tmp = other[['timestamp', 'close']].copy()
    tmp['timestamp'] = tmp['timestamp'].astype(str)
    tmp = tmp.rename(columns={'close': name})
    return df.merge(tmp, on='timestamp', how='left')


def build_feature_frame(
    ohlcv: pd.DataFrame,
    derivatives: pd.DataFrame,
    cfg: AppConfig,
    mark: pd.DataFrame | None = None,
    index: pd.DataFrame | None = None,
    orderbook: dict | None = None,
) -> pd.DataFrame:
    df = ohlcv.copy().reset_index(drop=True)
    df['timestamp'] = df['timestamp'].astype(str)
    for c in ['open','high','low','close','volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    ma_fast = int(cfg.get('features.ma_fast', 20))
    ma_slow = int(cfg.get('features.ma_slow', 50))
    ema_fast = int(cfg.get('features.ema_fast', 20))
    ema_slow = int(cfg.get('features.ema_slow', 50))
    atr_period = int(cfg.get('features.atr_period', 14))
    rsi_period = int(cfg.get('features.rsi_period', 14))
    adx_period = int(cfg.get('features.adx_period', 14))
    atr_pct_window = int(cfg.get('features.atr_percentile_window', 100))
    funding_z_window = int(cfg.get('features.funding_z_window', 100))

    df['ma20'] = sma(df['close'], ma_fast)
    df['ma50'] = sma(df['close'], ma_slow)
    df['ema20'] = ema(df['close'], ema_fast)
    df['ema50'] = ema(df['close'], ema_slow)
    df['atr'] = atr(df, atr_period)
    df['atr_pct_of_price'] = df['atr'] / df['close']
    df['atr_percentile'] = rolling_percentile(df['atr_pct_of_price'], atr_pct_window)
    df['rsi'] = rsi(df['close'], rsi_period)
    df['adx'] = adx(df, adx_period)
    df['volume_ma20'] = sma(df['volume'], 20)
    df['price_distance_ma20'] = (df['close'] - df['ma20']) / df['ma20']

    # Candle-derived indicators: no feed, so they carry real values wherever the
    # candles do (backtest and live alike). Warm-up stays NaN = indeterminate.
    macd_line, macd_signal, macd_hist = macd(
        df['close'],
        int(cfg.get('features.macd_fast', 12)),
        int(cfg.get('features.macd_slow', 26)),
        int(cfg.get('features.macd_signal', 9)),
    )
    df['macd'] = macd_line
    df['macd_signal'] = macd_signal
    df['macd_hist'] = macd_hist

    bb_period = int(cfg.get('features.bb_period', 20))
    bb_std = float(cfg.get('features.bb_std', 2.0))
    bb_upper, bb_lower, bb_width, bb_pct_b = bollinger(df['close'], bb_period, bb_std)
    df['bb_upper'] = bb_upper
    df['bb_lower'] = bb_lower
    df['bb_width_pct'] = bb_width
    df['bb_percent_b'] = bb_pct_b
    df['bb_width_percentile'] = rolling_percentile(df['bb_width_pct'], atr_pct_window)

    df['roc_4'] = roc(df['close'], int(cfg.get('features.roc_fast', 4)))
    df['roc_12'] = roc(df['close'], int(cfg.get('features.roc_slow', 12)))
    df['volume_zscore'] = zscore(df['volume'], int(cfg.get('features.volume_z_window', 20)))

    df = _merge_close_feature(df, mark, 'mark_price')
    df = _merge_close_feature(df, index, 'index_price')
    df['mark_price'] = pd.to_numeric(df.get('mark_price'), errors='coerce').ffill().fillna(df['close'])
    df['index_price'] = pd.to_numeric(df.get('index_price'), errors='coerce').ffill().fillna(df['close'])
    df['mark_index_basis_bps'] = (df['mark_price'] - df['index_price']) / df['index_price'].replace(0, np.nan) * 10000
    df['mark_last_basis_bps'] = (df['mark_price'] - df['close']) / df['close'].replace(0, np.nan) * 10000

    orderbook = orderbook or {}
    df['bid_price'] = orderbook.get('bid_price')
    df['ask_price'] = orderbook.get('ask_price')
    df['spread_bps'] = orderbook.get('spread_bps', 0)
    df['spread_bps'] = pd.to_numeric(df['spread_bps'], errors='coerce').fillna(0)

    if derivatives is not None and not derivatives.empty:
        der = derivatives.copy()
        der['timestamp'] = der['timestamp'].astype(str)
        keep = ['timestamp','funding_rate','open_interest','open_interest_base','oi_change_pct','long_liquidation','short_liquidation']
        der = der[[c for c in keep if c in der.columns]]
        df = df.merge(der, on='timestamp', how='left')
    else:
        for c in ['funding_rate','open_interest','open_interest_base','oi_change_pct','long_liquidation','short_liquidation']:
            df[c] = np.nan

    df['funding_rate'] = pd.to_numeric(df['funding_rate'], errors='coerce').fillna(0)
    funding_ma = df['funding_rate'].rolling(funding_z_window, min_periods=10).mean()
    funding_std = df['funding_rate'].rolling(funding_z_window, min_periods=10).std().replace(0, np.nan)
    df['funding_zscore'] = ((df['funding_rate'] - funding_ma) / funding_std).replace([np.inf, -np.inf], np.nan).fillna(0)

    df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').ffill().fillna(0)
    df['open_interest_base'] = pd.to_numeric(df.get('open_interest_base', 0), errors='coerce').ffill().fillna(0)
    df['oi_change_pct'] = pd.to_numeric(df['oi_change_pct'], errors='coerce').fillna(df['open_interest'].pct_change()).fillna(0)
    df['oi_change_4h_pct'] = df['open_interest'].pct_change(4).replace([np.inf, -np.inf], np.nan).fillna(0)
    df['long_liquidation'] = pd.to_numeric(df['long_liquidation'], errors='coerce').fillna(0)
    df['short_liquidation'] = pd.to_numeric(df['short_liquidation'], errors='coerce').fillna(0)

    liq_total = df['long_liquidation'] + df['short_liquidation']
    liq_ma = liq_total.rolling(50, min_periods=10).mean().replace(0, np.nan)
    df['liquidation_total'] = liq_total
    df['liquidation_spike_ratio'] = (liq_total / liq_ma).replace([np.inf, -np.inf], np.nan).fillna(0)
    df['liquidation_imbalance'] = (df['short_liquidation'] - df['long_liquidation']) / liq_total.replace(0, np.nan)
    df['liquidation_imbalance'] = df['liquidation_imbalance'].fillna(0)
    df['long_liquidation_spike'] = ((df['long_liquidation'] > df['long_liquidation'].rolling(50, min_periods=10).mean() * 3) & (df['long_liquidation'] > 0)).astype(int)
    df['short_liquidation_spike'] = ((df['short_liquidation'] > df['short_liquidation'].rolling(50, min_periods=10).mean() * 3) & (df['short_liquidation'] > 0)).astype(int)

    if bool(cfg.get('price_data.include_multi_timeframe_context', True)):
        mtf_context = build_multi_timeframe_context(cfg)
        df['mtf_alignment_score'] = float(mtf_context.get('alignment_score') or 0.0)
        df['mtf_bias'] = str(mtf_context.get('bias') or 'UNKNOWN')
        df['mtf_available'] = bool(mtf_context.get('available'))
        for tf, item in (mtf_context.get('timeframes') or {}).items():
            safe_tf = str(tf).replace(' ', '_').replace('/', '_')
            df[f'mtf_{safe_tf}_close'] = item.get('close')
            df[f'mtf_{safe_tf}_trend'] = item.get('trend')
            df[f'mtf_{safe_tf}_rsi'] = item.get('rsi')
            df[f'mtf_{safe_tf}_change_1'] = item.get('change_1')
    else:
        df['mtf_alignment_score'] = 0.0
        df['mtf_bias'] = 'DISABLED'
        df['mtf_available'] = False

    # Backtestable higher-timeframe trend, resampled from these same candles.
    # Unlike the mtf_* block above (a live scalar broadcast to every row) this is
    # per-row and look-ahead free, so it runs unconditionally — in the factory too.
    df = add_higher_timeframe_features(df, cfg)

    additional_snapshot = {}
    if isinstance(orderbook, dict):
        additional_snapshot = dict(orderbook.get('additional_feature_snapshot') or {})
        if not additional_snapshot:
            additional_snapshot = build_additional_feature_snapshot(orderbook.get('additional_feature_frames') or {})
    for key, value in additional_snapshot.items():
        if key in {'timestamp', 'source'}:
            df[f'additional_{key}'] = value
        elif key not in df.columns:
            df[key] = value
    for col in ['binance_derivatives_score', 'exchange_flow_score', 'etf_flow_score', 'stablecoin_liquidity_score']:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    adx_threshold = float(cfg.get('entry_policy.adx_trend_threshold', 20))
    df['market_regime'] = df.apply(lambda r: classify_market_regime(r, adx_threshold), axis=1)
    df['data_quality_status'] = np.where(df[['close','atr','rsi','adx']].isna().any(axis=1), 'WARMUP', 'OK')
    df['data_source'] = df.get('source', 'extended')
    return df


def latest_feature_snapshot(features: pd.DataFrame) -> dict:
    if features.empty:
        return {}
    return features.iloc[-1].replace({np.nan: None}).to_dict()
