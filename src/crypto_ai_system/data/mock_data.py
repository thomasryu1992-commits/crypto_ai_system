from __future__ import annotations

import numpy as np
import pandas as pd


def generate_mock_ohlcv(symbol: str = 'BTC-PERP', timeframe: str = 'PT1H', periods: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor('h'), periods=periods, freq='h')

    drift = np.zeros(periods)
    drift[:periods//4] = 0.0001
    drift[periods//4:periods//2] = 0.0011
    drift[periods//2:3*periods//4] = -0.0008
    drift[3*periods//4:] = 0.0004
    vol = np.linspace(0.006, 0.014, periods)
    shocks = rng.normal(drift, vol)
    close = 60000 * np.exp(np.cumsum(shocks))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0.003, 0.002, periods))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = rng.lognormal(mean=8.5, sigma=0.45, size=periods)

    return pd.DataFrame({
        'timestamp': idx.astype(str),
        'symbol': symbol,
        'exchange': 'extended',
        'exchange_market': 'BTC-USD',
        'timeframe': timeframe,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'source': 'sample_extended'
    })


def generate_mock_mark_index(ohlcv: pd.DataFrame, seed: int = 202) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    mark = ohlcv.copy()
    index = ohlcv.copy()
    mark_noise = rng.normal(0, 0.0008, len(ohlcv))
    index_noise = rng.normal(0, 0.0004, len(ohlcv))
    for c in ['open', 'high', 'low', 'close']:
        mark[c] = mark[c] * (1 + mark_noise)
        index[c] = index[c] * (1 + index_noise)
    mark['source'] = 'sample_extended_mark'
    index['source'] = 'sample_extended_index'
    return mark, index


def generate_mock_derivatives(ohlcv: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(ohlcv)
    returns = ohlcv['close'].pct_change().fillna(0).to_numpy()
    oi = 1_000_000_000 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, n)))
    funding = np.clip(rng.normal(0.00003, 0.00018, n) + returns * 0.01, -0.0012, 0.0012)
    long_liq = np.where(returns < -0.012, np.abs(returns) * rng.lognormal(18, 0.5, n), rng.lognormal(12, 0.6, n))
    short_liq = np.where(returns > 0.012, np.abs(returns) * rng.lognormal(18, 0.5, n), rng.lognormal(12, 0.6, n))
    df = pd.DataFrame({
        'timestamp': ohlcv['timestamp'],
        'symbol': ohlcv['symbol'],
        'exchange': ohlcv.get('exchange', 'extended'),
        'exchange_market': ohlcv.get('exchange_market', 'BTC-USD'),
        'timeframe': ohlcv['timeframe'],
        'funding_rate': funding,
        'open_interest': oi,
        'open_interest_base': oi / ohlcv['close'].to_numpy(),
        'long_liquidation': long_liq,
        'short_liquidation': short_liq,
        'source': 'sample_extended'
    })
    df['oi_change_pct'] = df['open_interest'].pct_change().fillna(0)
    return df
