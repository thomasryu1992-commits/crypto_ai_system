from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period, min_periods=period).mean()


def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False, min_periods=period).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).rolling(period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['high']
    low = df['low']
    close = df['close']
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = true_range(df)
    atr_ = tr.rolling(period, min_periods=period).sum()
    plus_di = 100 * plus_dm.rolling(period, min_periods=period).sum() / atr_.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(period, min_periods=period).sum() / atr_.replace(0, np.nan)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.rolling(period, min_periods=period).mean()


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram. NaN until the slow EMA has warmed up."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line, signal_line, macd_line - signal_line


def bollinger(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Upper, lower, width (% of mid), and %B (position within the band).

    %B is 1.0 at the upper band and 0.0 at the lower; a zero-width band leaves it
    NaN rather than dividing by zero, so a flat series stays indeterminate.
    """
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width_pct = (upper - lower) / mid.replace(0, np.nan)
    percent_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return upper, lower, width_pct, percent_b


def roc(close: pd.Series, period: int) -> pd.Series:
    """Rate of change over ``period`` bars, as a fraction (0.01 == +1%)."""
    return close.pct_change(period).replace([np.inf, -np.inf], np.nan)


def zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score. Zero-variance windows stay NaN (indeterminate)."""
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std().replace(0, np.nan)
    return ((series - mean) / std).replace([np.inf, -np.inf], np.nan)


def rolling_percentile(series: pd.Series, window: int = 100) -> pd.Series:
    def pct_rank(x):
        if len(x) == 0:
            return np.nan
        return pd.Series(x).rank(pct=True).iloc[-1]
    return series.rolling(window, min_periods=max(10, window // 5)).apply(pct_rank, raw=False)
