"""Higher-timeframe trend context derived from the base candles (no extra feeds).

The legacy ``mtf_*`` columns come from ``build_multi_timeframe_context``, which
fetches the *current* higher-timeframe state and broadcasts one scalar to every
row — useful for a live research note, useless (and look-ahead biased) for a
backtest. These ``htf_*`` columns are the backtestable replacement: the base
candle series is resampled up to 4h/1d, a trend is computed per higher-timeframe
bar, and each base row is joined to the most recent higher-timeframe bar that had
**already closed** at that row's timestamp.

That join is the whole point: a 4h bar opening at T is only known at T+4h, so it
is published at ``available_at = T + period`` and matched backward. A base row can
never see a bar that had not finished forming, in backtest or live, and both use
this same code path.

Warm-up and gaps stay NaN rather than a neutral constant: NaN is indeterminate to
the evaluator (fail-closed, no entry), whereas a constant would silently make a
condition always-true or always-false. A strategy referencing these features
therefore needs enough base candles to form the higher-timeframe bars — see
``CANDLE_FETCH_LIMIT``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.features.indicators import ema

# label -> (resample rule, bar period). Order fixes the alignment-score weighting.
HTF_SPECS: tuple[tuple[str, str, pd.Timedelta], ...] = (
    # Explicit-unit construction: kwarg/string forms hit NumPy's deprecated
    # 'generic' timedelta unit and will raise on a future NumPy.
    ("4h", "4h", pd.Timedelta(4, unit="h")),
    ("1d", "1D", pd.Timedelta(1, unit="D")),
)

HTF_TREND_COLUMNS: tuple[str, ...] = tuple(f"htf_{label}_trend" for label, _, _ in HTF_SPECS)
HTF_GAP_COLUMNS: tuple[str, ...] = tuple(f"htf_{label}_ema_gap_pct" for label, _, _ in HTF_SPECS)
HTF_COLUMNS: tuple[str, ...] = (*HTF_TREND_COLUMNS, *HTF_GAP_COLUMNS, "htf_alignment_score")

_TREND_SCORE = {"UP": 1.0, "DOWN": -1.0, "FLAT": 0.0}


def _blank(df: pd.DataFrame) -> pd.DataFrame:
    for col in HTF_TREND_COLUMNS:
        df[col] = None
    for col in HTF_GAP_COLUMNS:
        df[col] = np.nan
    df["htf_alignment_score"] = np.nan
    return df


def _trend_frame(
    ohlc: pd.DataFrame, rule: str, period: pd.Timedelta, fast: int, slow: int, flat_eps: float
) -> pd.DataFrame | None:
    """Resample to ``rule`` and return per-bar trend published at its close time."""
    bars = ohlc.resample(rule, label="left", closed="left").agg({"close": "last"}).dropna()
    if bars.empty:
        return None

    fast_ema = ema(bars["close"], fast)
    slow_ema = ema(bars["close"], slow)
    gap = (fast_ema - slow_ema) / slow_ema.replace(0, np.nan)

    trend = pd.Series(np.where(gap > flat_eps, "UP", np.where(gap < -flat_eps, "DOWN", "FLAT")), index=bars.index)
    trend = trend.where(gap.notna(), None)

    out = pd.DataFrame({"trend": trend, "gap": gap})
    # A bar opening at T is only known once it closes at T + period.
    out["available_at"] = out.index + period
    return out.reset_index(drop=True).sort_values("available_at")


def add_higher_timeframe_features(df: pd.DataFrame, cfg: AppConfig) -> pd.DataFrame:
    """Attach ``htf_*`` trend columns to ``df`` (which must carry ``timestamp``).

    Every column is NaN/None when the higher timeframe cannot be formed honestly
    (unparseable timestamps, too little history, or a base interval already at or
    above the target), so the evaluator treats it as indeterminate.
    """
    if df.empty or "timestamp" not in df.columns:
        return _blank(df)

    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    if ts.isna().any():
        return _blank(df)

    base_interval = ts.diff().median()
    if pd.isna(base_interval) or base_interval <= pd.Timedelta(0):
        return _blank(df)

    fast = int(cfg.get("features.htf_ema_fast", 5))
    slow = int(cfg.get("features.htf_ema_slow", 20))
    daily_fast = int(cfg.get("features.htf_daily_ema_fast", 3))
    daily_slow = int(cfg.get("features.htf_daily_ema_slow", 10))
    flat_eps = float(cfg.get("features.htf_flat_eps", 0.0005))

    ohlc = pd.DataFrame({"close": pd.to_numeric(df["close"], errors="coerce").to_numpy()}, index=ts)
    ohlc = ohlc[~ohlc.index.duplicated(keep="last")].sort_index()

    left = pd.DataFrame({"_ts": ts})
    left["_order"] = np.arange(len(left))
    left = left.sort_values("_ts")

    scores: list[pd.Series] = []
    for label, rule, period in HTF_SPECS:
        trend_col, gap_col = f"htf_{label}_trend", f"htf_{label}_ema_gap_pct"
        if period <= base_interval:
            # The base timeframe is already at/above this one — nothing to add.
            df[trend_col], df[gap_col] = None, np.nan
            scores.append(pd.Series(np.nan, index=df.index))
            continue

        f, s = (daily_fast, daily_slow) if label == "1d" else (fast, slow)
        bars = _trend_frame(ohlc, rule, period, f, s, flat_eps)
        if bars is None:
            df[trend_col], df[gap_col] = None, np.nan
            scores.append(pd.Series(np.nan, index=df.index))
            continue

        merged = pd.merge_asof(left, bars, left_on="_ts", right_on="available_at", direction="backward")
        merged = merged.sort_values("_order")
        df[trend_col] = merged["trend"].to_numpy()
        df[gap_col] = merged["gap"].to_numpy()
        scores.append(df[trend_col].map(_TREND_SCORE).astype(float))

    # Indeterminate on any leg: an "alignment" that ignores a missing timeframe
    # would overstate agreement.
    stacked = pd.concat(scores, axis=1)
    df["htf_alignment_score"] = stacked.mean(axis=1).where(stacked.notna().all(axis=1), np.nan)
    return df
