"""Funding-rate feature wiring: paged fetch, cache, honest alignment, templates.

funding_rate / funding_zscore left RUNTIME_UNAVAILABLE_FEATURES because the
adapter now aligns the real 8h funding-event series onto every frame. The
contract these tests pin: real values wherever events exist, NaN (indeterminate)
where they don't — never a constant — and no funding event visible to a bar that
opened before it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_ai_system.data.binance_futures_collector import (
    PUBLIC_FUNDING_PAGE_LIMIT,
    BinanceFuturesPublicClient,
)
from crypto_ai_system.data.candle_history import load_funding_history
from crypto_ai_system.strategy_factory.allowed_feature_registry import (
    RUNTIME_UNAVAILABLE_FEATURES,
    is_runtime_available_feature,
)
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame

_8H_MS = 8 * 3_600_000
_BASE_MS = 1_700_000_000_000


class _StubVenue:
    """Finite funding history honouring endTime/limit — but short-paging like the
    real endpoint, which returns fewer rows than asked even mid-history."""

    def __init__(self, total: int, page_cap: int = 500) -> None:
        self.times = [_BASE_MS + i * _8H_MS for i in range(total)]
        self.page_cap = page_cap
        self.calls = 0

    def get(self, path: str, params: dict) -> list:
        self.calls += 1
        limit = min(int(params.get("limit", PUBLIC_FUNDING_PAGE_LIMIT)), self.page_cap)
        end = params.get("endTime")
        eligible = [t for t in self.times if end is None or t <= int(end)]
        return [
            {"fundingTime": t, "fundingRate": "0.0001", "markPrice": "50000"}
            for t in eligible[-limit:]
        ]


def _client(venue: _StubVenue) -> BinanceFuturesPublicClient:
    client = BinanceFuturesPublicClient()
    client._get = venue.get  # type: ignore[method-assign]
    return client


def test_funding_history_pages_past_short_pages() -> None:
    """The endpoint short-pages (500 vs a 1000 ask); paging must continue anyway."""
    venue = _StubVenue(3000, page_cap=500)
    frame = _client(venue).funding_rate_history("BTCUSDT", 2500)
    assert len(frame) == 2500
    assert venue.calls >= 5


def test_funding_history_is_deduped_and_ascending() -> None:
    frame = _client(_StubVenue(2000)).funding_rate_history("BTCUSDT", 1500)
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    assert ts.is_monotonic_increasing and not ts.duplicated().any()


def test_funding_history_stops_when_venue_runs_out() -> None:
    frame = _client(_StubVenue(300)).funding_rate_history("BTCUSDT", 5000)
    assert len(frame) == 300


def test_funding_cache_roundtrip(tmp_path) -> None:
    class _CountingClient:
        fetches = 0

        def funding_rate_history(self, symbol, records, **kw):
            self.fetches += 1
            end = pd.Timestamp.now(tz="UTC").floor("h")
            return pd.DataFrame([
                {"timestamp": str(end - pd.Timedelta(hours=8 * (records - 1 - i))),
                 "funding_rate": 0.0001}
                for i in range(records)
            ])

    client = _CountingClient()
    _, source = load_funding_history("BTCUSDT", 100, cache_dir=tmp_path, client=client)
    assert source == "fetch"
    _, source = load_funding_history("BTCUSDT", 100, cache_dir=tmp_path, client=client)
    assert source == "cache" and client.fetches == 1


def _candles(n: int) -> list[dict]:
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    close = 60000 + np.linspace(0, 2000, n)
    return [
        {"timestamp": str(t), "open": c - 20, "high": c + 60, "low": c - 60, "close": c, "volume": 100.0}
        for t, c in zip(ts, close)
    ]


def _funding_frame(start: str, events: int, rate: float = 0.0001) -> pd.DataFrame:
    ts = pd.date_range(start, periods=events, freq="8h", tz="UTC")
    return pd.DataFrame({"timestamp": [str(t) for t in ts], "funding_rate": rate})


def test_funding_aligns_backward_onto_every_bar() -> None:
    frame = build_backtest_frame(
        _candles(300), funding_loader=lambda: _funding_frame("2023-12-01", 400)
    )
    assert frame["funding_rate"].notna().all()


def test_bars_before_the_first_funding_event_stay_nan() -> None:
    """No constant backfill: pre-history bars must be indeterminate."""
    frame = build_backtest_frame(
        _candles(300), funding_loader=lambda: _funding_frame("2024-01-05", 100)
    )
    first_event = pd.Timestamp("2024-01-05", tz="UTC")
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    assert frame.loc[ts < first_event, "funding_rate"].isna().all()
    assert frame.loc[ts >= first_event, "funding_rate"].notna().all()


def test_no_funding_event_leaks_into_earlier_bars() -> None:
    """A funding spike is visible only from its own bar onward (merge backward)."""
    funding = _funding_frame("2023-12-01", 400)
    spike_at = pd.Timestamp("2024-01-08 08:00:00", tz="UTC")
    funding.loc[pd.to_datetime(funding["timestamp"]) == spike_at, "funding_rate"] = 0.01

    frame = build_backtest_frame(_candles(300), funding_loader=lambda: funding)
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    assert (frame.loc[ts < spike_at, "funding_rate"] < 0.01).all()
    assert frame.loc[ts == spike_at, "funding_rate"].iloc[0] == pytest.approx(0.01)


def test_funding_loader_failure_yields_nan_not_constant() -> None:
    def boom():
        raise RuntimeError("venue down")

    frame = build_backtest_frame(_candles(100), funding_loader=boom)
    assert frame["funding_rate"].isna().all()
    assert frame["funding_zscore"].isna().all()


def test_legacy_path_without_funding_series_is_unchanged() -> None:
    """Callers that never pass funding keep the 0-filled legacy behavior."""
    from crypto_ai_system.config import load_config
    from crypto_ai_system.features.feature_store import build_feature_frame

    cfg = load_config(".")
    ohlcv = pd.DataFrame(_candles(50))
    frame = build_feature_frame(ohlcv, pd.DataFrame(), cfg)
    assert (frame["funding_rate"] == 0).all()


def test_funding_features_are_registered_runtime_available() -> None:
    for feature in ("funding_rate", "funding_zscore"):
        assert feature not in RUNTIME_UNAVAILABLE_FEATURES
        assert is_runtime_available_feature(feature)


def test_funding_templates_generate_and_validate() -> None:
    from crypto_ai_system.strategy_factory.strategy_generator_agent import generate_batch
    from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
    from crypto_ai_system.strategy_factory.strategy_template_library import TEMPLATES, retimed
    from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy

    for family in ("funding_fade_long", "funding_fade_short"):
        template = retimed(TEMPLATES[family], "1d")
        batch = generate_batch("gen_f", seed=3, count=1, templates=(template,))
        spec = batch["specs"][0]
        spec = spec if isinstance(spec, StrategySpec) else StrategySpec.from_dict(spec)
        verdict = validate_strategy(spec)
        assert verdict["approved_for_backtest"], verdict["block_reasons"]
