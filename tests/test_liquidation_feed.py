"""Liquidation feature wiring: daily Coinalyze series, cache, honest alignment.

The liquidation_* family left RUNTIME_UNAVAILABLE_FEATURES because the adapter
now aligns the daily long/short liquidation series onto every frame. The
contract these tests pin: real values wherever closed days exist, NaN
(indeterminate) where they don't — never a constant — no day's aggregate
visible to an earlier bar, and the still-forming current day dropped at the
source.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_ai_system.data.candle_history import load_liquidation_history
from crypto_ai_system.strategy_factory.allowed_feature_registry import (
    RUNTIME_UNAVAILABLE_FEATURES,
    is_runtime_available_feature,
)
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame

LIQ_FEATURES = (
    "long_liquidation", "short_liquidation", "liquidation_total",
    "liquidation_spike_ratio", "liquidation_imbalance",
    "long_liquidation_spike", "short_liquidation_spike",
)


class _StubCoinalyze:
    """Daily liquidation history ending at a configurable newest bucket."""

    def __init__(self, days: int, newest: pd.Timestamp | None = None) -> None:
        end = newest if newest is not None else pd.Timestamp.now(tz="UTC").normalize()
        self.ts = pd.date_range(end=end, periods=days, freq="1D")
        self.fetches = 0

    def get_liquidation_history(self, symbol, interval="daily", limit=500, from_ts=None, to_ts=None):
        self.fetches += 1
        return pd.DataFrame([
            {"timestamp": str(t), "coinalyze_symbol": symbol,
             "long_liquidation": 1000.0 + i, "short_liquidation": 800.0 + i}
            for i, t in enumerate(self.ts)
        ])


def test_liquidation_cache_roundtrip(tmp_path) -> None:
    client = _StubCoinalyze(120, newest=pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(1, unit="D"))
    rows, source = load_liquidation_history("BTCUSDT", 100, cache_dir=tmp_path, client=client)
    assert source == "fetch" and len(rows) == 100
    rows, source = load_liquidation_history("BTCUSDT", 100, cache_dir=tmp_path, client=client)
    assert source == "cache" and client.fetches == 1


def test_unclosed_current_day_is_dropped(tmp_path) -> None:
    """The venue returns the in-progress day; consumers must never see it."""
    today = pd.Timestamp.now(tz="UTC").normalize()
    client = _StubCoinalyze(50, newest=today)
    rows, _ = load_liquidation_history("BTCUSDT", 100, cache_dir=tmp_path, client=client)
    newest = pd.to_datetime(rows[-1]["timestamp"], utc=True)
    assert newest < today


def test_missing_api_key_raises(tmp_path, monkeypatch) -> None:
    """No key -> the loader raises; the adapter is what turns that into NaN."""
    monkeypatch.delenv("COINALYZE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        load_liquidation_history("BTCUSDT", 10, cache_dir=tmp_path)


def _daily_candles(n: int, start: str = "2024-01-01") -> list[dict]:
    ts = pd.date_range(start, periods=n, freq="1D", tz="UTC")
    close = 60000 + np.linspace(0, 2000, n)
    return [
        {"timestamp": str(t), "open": c - 20, "high": c + 60, "low": c - 60, "close": c, "volume": 100.0}
        for t, c in zip(ts, close)
    ]


def _liq_frame(start: str, days: int, long=1000.0, short=800.0) -> pd.DataFrame:
    ts = pd.date_range(start, periods=days, freq="1D", tz="UTC")
    return pd.DataFrame({
        "timestamp": [str(t) for t in ts],
        "long_liquidation": long,
        "short_liquidation": short,
    })


def _frame(candles, liq_loader):
    return build_backtest_frame(
        candles,
        funding_loader=lambda: pd.DataFrame(),
        liquidation_loader=liq_loader,
    )


def test_liquidations_align_daily_onto_bars() -> None:
    frame = _frame(_daily_candles(200), lambda: _liq_frame("2023-12-01", 300))
    assert frame["long_liquidation"].notna().all()
    assert frame["short_liquidation"].notna().all()
    assert (frame["liquidation_total"] == 1800.0).all()


def test_bars_before_the_first_liquidation_day_stay_nan() -> None:
    """No constant backfill: pre-history bars must be indeterminate."""
    frame = _frame(_daily_candles(200), lambda: _liq_frame("2024-02-01", 300))
    first = pd.Timestamp("2024-02-01", tz="UTC")
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    assert frame.loc[ts < first, "long_liquidation"].isna().all()
    assert frame.loc[ts >= first, "long_liquidation"].notna().all()


def test_no_liquidation_day_leaks_into_earlier_bars() -> None:
    """A liquidation spike is visible only from its own day onward."""
    liq = _liq_frame("2023-12-01", 300)
    spike_at = pd.Timestamp("2024-03-01", tz="UTC")
    liq.loc[pd.to_datetime(liq["timestamp"], utc=True) == spike_at, "long_liquidation"] = 99000.0

    frame = _frame(_daily_candles(200), lambda: liq)
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    assert (frame.loc[ts < spike_at, "long_liquidation"] < 99000.0).all()
    assert frame.loc[ts == spike_at, "long_liquidation"].iloc[0] == pytest.approx(99000.0)


def test_liquidation_loader_failure_yields_nan_not_constant() -> None:
    def boom():
        raise RuntimeError("coinalyze down")

    frame = _frame(_daily_candles(100), boom)
    for col in LIQ_FEATURES:
        assert frame[col].isna().all(), col


def test_spike_flags_stay_indeterminate_where_inputs_are_unknown() -> None:
    """NaN input must not read as 'no spike' — that would be a constant lie."""
    frame = _frame(_daily_candles(200), lambda: _liq_frame("2024-02-01", 300))
    first = pd.Timestamp("2024-02-01", tz="UTC")
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    assert frame.loc[ts < first, "long_liquidation_spike"].isna().all()
    assert frame.loc[ts >= first, "long_liquidation_spike"].notna().all()


def test_legacy_path_without_liquidation_series_is_unchanged() -> None:
    """Callers that never pass liquidations keep the 0-filled legacy behavior."""
    from crypto_ai_system.config import load_config
    from crypto_ai_system.features.feature_store import build_feature_frame

    cfg = load_config(".")
    ohlcv = pd.DataFrame(_daily_candles(60))
    frame = build_feature_frame(ohlcv, pd.DataFrame(), cfg)
    assert (frame["long_liquidation"] == 0).all()
    assert (frame["liquidation_spike_ratio"] == 0).all()
    assert frame["long_liquidation_spike"].isin((0, 1)).all()


def test_liquidation_features_are_registered_runtime_available() -> None:
    for feature in LIQ_FEATURES:
        assert feature not in RUNTIME_UNAVAILABLE_FEATURES, feature
        assert is_runtime_available_feature(feature), feature


def test_validator_accepts_a_liquidation_spec() -> None:
    from crypto_ai_system.strategy_factory.rule_miner import rule_set_to_spec_dict
    from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
    from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy

    rule_set = {
        "direction": "short",
        "conditions": [
            {"feature": "liquidation_spike_ratio", "comparison": ">=", "value": 2.5},
            {"feature": "rsi", "comparison": ">=", "value": 60.0},
        ],
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.2, "target_atr": 3.0, "max_holding_bars": 24},
    }
    spec_dict = rule_set_to_spec_dict(
        rule_set, strategy_id="T001", generation_id="TEST",
        symbol="BTCUSDT", timeframe="1d", search_evaluations=1,
    )
    verdict = validate_strategy(StrategySpec.from_dict(spec_dict))
    assert verdict["approved_for_backtest"], verdict["block_reasons"]


def test_miner_pool_draws_liquidation_conditions() -> None:
    from crypto_ai_system.strategy_factory.rule_miner import build_condition_pool

    frame = _frame(_daily_candles(200), lambda: _liq_frame("2023-12-01", 300))
    features = {c["feature"] for c in build_condition_pool(frame)}
    assert "liquidation_spike_ratio" in features
    assert "liquidation_imbalance" in features
