"""Contract tests for the candle-derived indicator + higher-timeframe features.

The point of these features is that they are *honest*: real values wherever the
candles support them, indeterminate (NaN/None) where they don't, and identical in
backtest and live. These tests pin exactly that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_ai_system.features.higher_timeframe import HTF_COLUMNS
from crypto_ai_system.strategy_factory.allowed_feature_registry import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    RUNTIME_UNAVAILABLE_FEATURES,
    is_runtime_available_feature,
)
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame

_CANDLE_INDICATORS = ("macd", "macd_signal", "macd_hist", "bb_percent_b", "roc_4", "volume_zscore")


def _candles(n: int, *, reverse_at: float = 0.5) -> list[dict]:
    """Hourly candles that trend up then down, so both HTF directions appear."""
    ts = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    cut = int(n * reverse_at)
    trend = np.concatenate([np.linspace(0, 4000, cut), np.linspace(4000, 1000, n - cut)])
    close = 60000 + trend + np.sin(np.arange(n) / 7) * 120
    return [
        {"timestamp": str(t), "open": c - 20, "high": c + 60, "low": c - 60, "close": c, "volume": 100 + i % 40}
        for i, (t, c) in enumerate(zip(ts, close))
    ]


def test_candle_indicators_carry_real_values() -> None:
    frame = build_backtest_frame(_candles(300))
    for col in _CANDLE_INDICATORS:
        assert frame[col].notna().sum() > 100, f"{col} should be populated from candles alone"
        assert frame[col].dropna().nunique() > 1, f"{col} must vary, not be a constant fallback"


def test_higher_timeframe_trend_populates_with_enough_history() -> None:
    frame = build_backtest_frame(_candles(600))
    assert set(frame["htf_4h_trend"].dropna().unique()) <= {"UP", "DOWN", "FLAT"}
    assert set(frame["htf_1d_trend"].dropna().unique()) <= {"UP", "DOWN", "FLAT"}
    # The series reverses, so both directions must be observed on the daily.
    assert {"UP", "DOWN"} <= set(frame["htf_1d_trend"].dropna().unique())
    align = frame["htf_alignment_score"].dropna()
    assert not align.empty and align.min() >= -1.0 and align.max() <= 1.0


def test_daily_htf_is_indeterminate_when_history_is_too_short() -> None:
    """200 candles cannot form the daily EMA — NaN, never a neutral constant."""
    frame = build_backtest_frame(_candles(200))
    assert frame["htf_1d_trend"].notna().sum() == 0
    assert frame["htf_alignment_score"].notna().sum() == 0
    # The 4h leg still works at that length.
    assert frame["htf_4h_trend"].notna().sum() > 0


def test_htf_alignment_is_indeterminate_when_a_leg_is_missing() -> None:
    frame = build_backtest_frame(_candles(200))
    has_4h = frame["htf_4h_trend"].notna()
    assert has_4h.any()
    # 4h known but 1d unknown must not yield an "aligned" score.
    assert frame.loc[has_4h, "htf_alignment_score"].isna().all()


def test_features_are_look_ahead_free() -> None:
    """Truncating the future must not change any already-computed row."""
    candles = _candles(600)
    cut = 420
    full = build_backtest_frame(candles).iloc[:cut].reset_index(drop=True)
    truncated = build_backtest_frame(candles[:cut]).reset_index(drop=True)

    for col in (*_CANDLE_INDICATORS, *HTF_COLUMNS):
        left, right = full[col], truncated[col]
        assert (left.astype(str) == right.astype(str)).all(), f"{col} leaks future information"


def test_unparseable_timestamps_fail_closed() -> None:
    candles = _candles(300)
    candles[10]["timestamp"] = "not-a-timestamp"
    frame = build_backtest_frame(candles)
    for col in HTF_COLUMNS:
        assert frame[col].isna().all(), f"{col} must be indeterminate on bad timestamps"


def test_base_timeframe_at_or_above_target_is_indeterminate() -> None:
    """Daily base candles cannot be resampled up to a 4h view."""
    ts = pd.date_range("2026-01-01", periods=60, freq="1D", tz="UTC")
    close = 60000 + np.linspace(0, 3000, 60)
    candles = [
        {"timestamp": str(t), "open": c - 20, "high": c + 60, "low": c - 60, "close": c, "volume": 100}
        for t, c in zip(ts, close)
    ]
    frame = build_backtest_frame(candles)
    assert frame["htf_4h_trend"].isna().all()


@pytest.mark.parametrize("feature", [*_CANDLE_INDICATORS, "htf_alignment_score", "htf_4h_ema_gap_pct"])
def test_new_numeric_features_are_registered_and_runtime_available(feature: str) -> None:
    assert feature in NUMERIC_FEATURES
    assert feature not in RUNTIME_UNAVAILABLE_FEATURES
    assert is_runtime_available_feature(feature)


@pytest.mark.parametrize("feature", ["htf_4h_trend", "htf_1d_trend"])
def test_new_categorical_features_are_registered(feature: str) -> None:
    assert CATEGORICAL_FEATURES[feature] == frozenset({"UP", "DOWN", "FLAT"})
    assert is_runtime_available_feature(feature)


def test_registered_features_actually_exist_in_the_frame() -> None:
    """The registry's promise: a spec may only reference an emitted column."""
    frame = build_backtest_frame(_candles(600))
    for feature in (*_CANDLE_INDICATORS, *HTF_COLUMNS):
        assert feature in frame.columns
