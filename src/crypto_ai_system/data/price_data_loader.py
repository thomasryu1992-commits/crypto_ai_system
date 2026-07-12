from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from crypto_ai_system.config import AppConfig


TIMEFRAME_TO_EXTENDED = {
    '15m': 'PT15M',
    '1h': 'PT1H',
    '4h': 'PT4H',
    '1d': 'P1D',
    '3d': 'P3D',
    '1w': 'P1W',
    '1m': 'P1M',
}

DEFAULT_PRICE_FILES = {
    '15m': 'btcusdtp_15m.csv',
    '1h': 'btcusdtp_1h.csv',
    '4h': 'btcusdtp_4h.csv',
    '1d': 'btcusdtp_1d.csv',
    '3d': 'btcusdtp_3d.csv',
    '1w': 'btcusdtp_1w.csv',
    '1m': 'btcusdtp_1m.csv',
}


@dataclass(frozen=True)
class PriceTimeframeSummary:
    timeframe: str
    rows: int
    latest_timestamp: str
    close: float | None
    change_1: float | None
    change_3: float | None
    change_10: float | None
    ema20: float | None
    ema50: float | None
    rsi: float | None
    cvd: float | None
    trend: str
    score: float
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _price_data_dir(cfg: AppConfig) -> Path:
    configured = cfg.get('price_data.directory', 'data/price_data/BINANCE_BTCUSDT_P')
    return (cfg.root / configured).resolve()


def _as_timestamp(series: pd.Series) -> pd.Series:
    # TradingView exports seconds in the provided files. This also tolerates ms.
    numeric = pd.to_numeric(series, errors='coerce')
    unit = 'ms' if numeric.dropna().median() and numeric.dropna().median() > 10_000_000_000 else 's'
    return pd.to_datetime(numeric, unit=unit, utc=True, errors='coerce').astype(str)


def _safe_pct_change(values: pd.Series, periods: int) -> float | None:
    if len(values) <= periods:
        return None
    cur = pd.to_numeric(values.iloc[-1], errors='coerce')
    prev = pd.to_numeric(values.iloc[-1 - periods], errors='coerce')
    if pd.isna(cur) or pd.isna(prev) or float(prev) == 0:
        return None
    return float((cur - prev) / prev)


def _last_number(df: pd.DataFrame, column: str) -> float | None:
    if column not in df.columns or df.empty:
        return None
    value = pd.to_numeric(df[column], errors='coerce').dropna()
    if value.empty:
        return None
    return float(value.iloc[-1])


def normalize_tradingview_price_csv(path: str | Path, timeframe: str, cfg: AppConfig) -> pd.DataFrame:
    """Normalize the uploaded TradingView/Binance BTCUSDT.P CSV into internal OHLCV format.

    The source CSV intentionally remains included under data/price_data, but all analysis
    uses this normalized schema so it can be merged with Extended/Coinalyze data.
    """
    p = Path(path)
    df = pd.read_csv(p)
    if 'time' not in df.columns:
        raise ValueError(f'Missing required time column in price data: {p}')

    out = pd.DataFrame()
    out['timestamp'] = _as_timestamp(df['time'])
    out['symbol'] = cfg.get('data.canonical_symbol', 'BTC-PERP')
    out['exchange'] = 'binance'
    out['exchange_market'] = 'BTCUSDT.P'
    out['timeframe'] = TIMEFRAME_TO_EXTENDED.get(timeframe, timeframe)
    for src, dst in [('open', 'open'), ('high', 'high'), ('low', 'low'), ('close', 'close'), ('Volume', 'volume')]:
        out[dst] = pd.to_numeric(df.get(src), errors='coerce')

    # Keep useful TradingView-derived context when present.
    out['source'] = f'price_data_binance_tradingview_{timeframe}'
    if 'RSI' in df.columns:
        out['tv_rsi'] = pd.to_numeric(df['RSI'], errors='coerce')
    if 'CVD' in df.columns:
        out['cvd'] = pd.to_numeric(df['CVD'], errors='coerce')

    ema_cols = [c for c in df.columns if c == 'EMA' or c.startswith('EMA.')]
    for idx, col in enumerate(ema_cols[:5], start=1):
        out[f'tv_ema_{idx}'] = pd.to_numeric(df[col], errors='coerce')

    oi_map = {
        'Open Interest (열기)': 'open_interest_open',
        'Open Interest (고가': 'open_interest_high',
        'Open Interest (저가)': 'open_interest_low',
        'Open Interest (닫기)': 'open_interest_close',
    }
    for src, dst in oi_map.items():
        if src in df.columns:
            out[dst] = pd.to_numeric(df[src], errors='coerce')

    out = out.dropna(subset=['timestamp', 'open', 'high', 'low', 'close']).sort_values('timestamp').reset_index(drop=True)
    limit = int(cfg.get('data.limit', 500))
    if limit > 0:
        out = out.tail(limit).reset_index(drop=True)
    return out


def load_price_history_bundle(cfg: AppConfig) -> Dict[str, pd.DataFrame]:
    if not bool(cfg.get('price_data.enabled', True)):
        return {}

    base = _price_data_dir(cfg)
    files = cfg.get('price_data.files', {}) or DEFAULT_PRICE_FILES
    bundle: Dict[str, pd.DataFrame] = {}
    for tf, filename in files.items():
        path = base / str(filename)
        if not path.exists():
            continue
        try:
            bundle[str(tf)] = normalize_tradingview_price_csv(path, str(tf), cfg)
        except Exception:
            # One broken timeframe must not break the whole system.
            continue
    return bundle


def select_primary_ohlcv_from_price_bundle(cfg: AppConfig, bundle: Dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    bundle = bundle if bundle is not None else load_price_history_bundle(cfg)
    primary = str(cfg.get('price_data.primary_timeframe', '1h')).lower()
    if primary in bundle and not bundle[primary].empty:
        return bundle[primary].copy()
    # Stable fallback order when the configured primary is absent.
    for tf in ['1h', '4h', '15m', '1d', '3d', '1w', '1m']:
        if tf in bundle and not bundle[tf].empty:
            return bundle[tf].copy()
    return pd.DataFrame()


def build_derivatives_from_price_data(ohlcv: pd.DataFrame, cfg: AppConfig) -> pd.DataFrame:
    if ohlcv is None or ohlcv.empty:
        return pd.DataFrame(columns=['timestamp', 'funding_rate', 'open_interest'])
    df = pd.DataFrame({
        'timestamp': ohlcv['timestamp'],
        'symbol': cfg.get('data.canonical_symbol', 'BTC-PERP'),
        'exchange': 'binance',
        'exchange_market': 'BTCUSDT.P',
        'timeframe': ohlcv.get('timeframe', cfg.get('data.timeframe', 'PT1H')),
        'funding_rate': 0.0,
        'source': 'price_data_binance_tradingview',
    })
    oi = pd.to_numeric(ohlcv.get('open_interest_close'), errors='coerce') if 'open_interest_close' in ohlcv.columns else pd.Series([np.nan] * len(ohlcv))
    df['open_interest'] = oi.ffill().fillna(0)
    close = pd.to_numeric(ohlcv.get('close'), errors='coerce').replace(0, np.nan)
    df['open_interest_base'] = (df['open_interest'] / close).replace([np.inf, -np.inf], np.nan).fillna(0)
    df['oi_change_pct'] = df['open_interest'].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
    df['long_liquidation'] = 0.0
    df['short_liquidation'] = 0.0
    return df.reset_index(drop=True)


def summarize_price_timeframe(timeframe: str, df: pd.DataFrame) -> PriceTimeframeSummary:
    close = pd.to_numeric(df['close'], errors='coerce') if not df.empty else pd.Series(dtype=float)
    ema20 = close.ewm(span=20, adjust=False).mean() if not close.empty else pd.Series(dtype=float)
    ema50 = close.ewm(span=50, adjust=False).mean() if not close.empty else pd.Series(dtype=float)
    latest_close = float(close.dropna().iloc[-1]) if not close.dropna().empty else None
    latest_ema20 = float(ema20.dropna().iloc[-1]) if not ema20.dropna().empty else None
    latest_ema50 = float(ema50.dropna().iloc[-1]) if not ema50.dropna().empty else None
    rsi = _last_number(df, 'tv_rsi')
    cvd = _last_number(df, 'cvd')

    trend = 'MIXED'
    score = 0.0
    if latest_close is not None and latest_ema20 is not None and latest_ema50 is not None:
        if latest_close > latest_ema20 > latest_ema50:
            trend, score = 'BULLISH', 1.0
        elif latest_close < latest_ema20 < latest_ema50:
            trend, score = 'BEARISH', -1.0
        elif latest_close > latest_ema20:
            trend, score = 'BULLISH_MIXED', 0.5
        elif latest_close < latest_ema20:
            trend, score = 'BEARISH_MIXED', -0.5

    return PriceTimeframeSummary(
        timeframe=timeframe,
        rows=int(len(df)),
        latest_timestamp=str(df['timestamp'].iloc[-1]) if not df.empty else '',
        close=latest_close,
        change_1=_safe_pct_change(close, 1),
        change_3=_safe_pct_change(close, 3),
        change_10=_safe_pct_change(close, 10),
        ema20=latest_ema20,
        ema50=latest_ema50,
        rsi=rsi,
        cvd=cvd,
        trend=trend,
        score=float(score),
        source=str(df.get('source', pd.Series(['price_data'])).iloc[-1]) if not df.empty else 'price_data',
    )


def build_multi_timeframe_context(cfg: AppConfig, bundle: Dict[str, pd.DataFrame] | None = None) -> Dict[str, Any]:
    bundle = bundle if bundle is not None else load_price_history_bundle(cfg)
    if not bundle:
        return {'enabled': bool(cfg.get('price_data.enabled', True)), 'available': False, 'timeframes': {}, 'alignment_score': 0.0, 'bias': 'UNKNOWN'}

    weights = cfg.get('price_data.timeframe_weights', {}) or {
        '15m': 0.5,
        '1h': 1.0,
        '4h': 1.5,
        '1d': 2.0,
        '3d': 2.0,
        '1w': 2.5,
        '1m': 2.5,
    }
    summaries: Dict[str, Dict[str, Any]] = {}
    numerator = 0.0
    denominator = 0.0
    for tf, df in bundle.items():
        if df is None or df.empty:
            continue
        summary = summarize_price_timeframe(tf, df).to_dict()
        summaries[tf] = summary
        weight = float(weights.get(tf, 1.0))
        numerator += float(summary.get('score') or 0.0) * weight
        denominator += abs(weight)

    alignment = numerator / denominator if denominator else 0.0
    bias = 'BULLISH' if alignment >= 0.35 else 'BEARISH' if alignment <= -0.35 else 'MIXED'
    return {
        'enabled': True,
        'available': bool(summaries),
        'primary_timeframe': cfg.get('price_data.primary_timeframe', '1h'),
        'timeframes': summaries,
        'alignment_score': float(round(alignment, 6)),
        'bias': bias,
        'source': 'embedded_binance_tradingview_price_data',
    }
