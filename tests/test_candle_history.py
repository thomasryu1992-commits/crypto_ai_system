"""Paged deep-history fetch + on-disk cache.

A single klines call caps at 1500 rows (~2 months of 1h candles), which yields
far too few trades to judge a strategy. These tests pin the paging that gets past
that cap without gaps, duplicates, or an infinite loop, and the cache that keeps
repeated factory runs off the network.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from crypto_ai_system.data.binance_futures_collector import (
    PUBLIC_KLINE_PAGE_LIMIT,
    BinanceFuturesPublicClient,
)
from crypto_ai_system.data.candle_history import load_candle_history

_HOUR_MS = 3_600_000
_BASE_MS = 1_700_000_000_000


def _kline(open_ms: int) -> list:
    return [open_ms, "100.0", "101.0", "99.0", "100.5", "10.0"]


class _StubVenue:
    """Serves a finite hourly history, honouring endTime/limit like the venue."""

    def __init__(self, total_bars: int) -> None:
        self.all_open_ms = [_BASE_MS + i * _HOUR_MS for i in range(total_bars)]
        self.calls: list[dict] = []

    def get(self, path: str, params: dict) -> list:
        self.calls.append(dict(params))
        limit = int(params.get("limit", PUBLIC_KLINE_PAGE_LIMIT))
        end_time = params.get("endTime")
        eligible = [t for t in self.all_open_ms if end_time is None or t <= int(end_time)]
        return [_kline(t) for t in eligible[-limit:]]


def _client(venue: _StubVenue) -> BinanceFuturesPublicClient:
    client = BinanceFuturesPublicClient()
    client._get = venue.get  # type: ignore[method-assign]
    return client


def test_history_pages_past_the_per_call_cap() -> None:
    venue = _StubVenue(5000)
    frame = _client(venue).klines_history("BTCUSDT", "1h", 4000)

    assert len(frame) == 4000
    assert len(venue.calls) > 1, "must page; one call cannot exceed the venue cap"
    assert all(c["limit"] <= PUBLIC_KLINE_PAGE_LIMIT for c in venue.calls)


def test_history_is_contiguous_deduped_and_oldest_first() -> None:
    frame = _client(_StubVenue(5000)).klines_history("BTCUSDT", "1h", 4000)

    ts = pd.to_datetime(frame["timestamp"], utc=True)
    assert ts.is_monotonic_increasing
    assert not ts.duplicated().any()
    gaps = ts.diff().dropna().unique()
    assert list(gaps) == [pd.Timedelta(hours=1)], "paging must not tear the series"


def test_history_returns_the_most_recent_bars() -> None:
    venue = _StubVenue(5000)
    frame = _client(venue).klines_history("BTCUSDT", "1h", 2000)

    newest = pd.to_datetime(frame["timestamp"].iloc[-1], utc=True)
    expected = pd.to_datetime(venue.all_open_ms[-1], unit="ms", utc=True)
    assert newest == expected


def test_history_stops_when_the_venue_runs_out() -> None:
    """Asking for more than exists returns what exists, not an endless loop."""
    frame = _client(_StubVenue(800)).klines_history("BTCUSDT", "1h", 5000)
    assert len(frame) == 800


def test_history_stops_when_a_page_makes_no_backward_progress() -> None:
    class _StuckVenue(_StubVenue):
        def get(self, path: str, params: dict) -> list:
            self.calls.append(dict(params))
            return [_kline(self.all_open_ms[-1])]  # always the same bar

    venue = _StuckVenue(5000)
    frame = _client(venue).klines_history("BTCUSDT", "1h", 4000)

    assert len(frame) == 1
    assert len(venue.calls) <= 2, "must not spin when paging stalls"


def test_history_empty_response_yields_empty_frame() -> None:
    class _EmptyVenue(_StubVenue):
        def get(self, path: str, params: dict) -> list:
            return []

    assert _client(_EmptyVenue(0)).klines_history("BTCUSDT", "1h", 100).empty


def _fresh_rows(n: int) -> list[dict]:
    end = pd.Timestamp.now(tz="UTC").floor("h")
    return [
        {"timestamp": str(end - pd.Timedelta(hours=n - 1 - i)), "open": 1.0, "high": 1.0,
         "low": 1.0, "close": 1.0, "volume": 1.0}
        for i in range(n)
    ]


def _write(tmp_path, rows: list[dict]) -> None:
    (tmp_path / "BTCUSDT_1h.json").write_text(
        json.dumps({"version": "candle_history.v1", "candles": rows}), encoding="utf-8"
    )


class _CountingClient:
    def __init__(self) -> None:
        self.fetches = 0

    def klines_history(self, symbol, interval, bars, **kw):
        self.fetches += 1
        return pd.DataFrame(_fresh_rows(bars))


def test_cache_is_reused_when_fresh_and_deep_enough(tmp_path) -> None:
    _write(tmp_path, _fresh_rows(500))
    client = _CountingClient()

    rows, source = load_candle_history("BTCUSDT", "1h", 300, cache_dir=tmp_path, client=client)

    assert source == "cache" and client.fetches == 0
    assert len(rows) == 300, "must return the newest N, not the whole cache"


def test_cache_is_refetched_when_too_shallow(tmp_path) -> None:
    _write(tmp_path, _fresh_rows(100))
    client = _CountingClient()

    _, source = load_candle_history("BTCUSDT", "1h", 500, cache_dir=tmp_path, client=client)

    assert source == "fetch" and client.fetches == 1


def test_cache_is_refetched_when_stale(tmp_path) -> None:
    stale = _fresh_rows(500)
    old = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=3)
    stale[-1] = {**stale[-1], "timestamp": str(old)}
    _write(tmp_path, stale)
    client = _CountingClient()

    _, source = load_candle_history("BTCUSDT", "1h", 300, cache_dir=tmp_path, client=client)

    assert source == "fetch" and client.fetches == 1


def test_refresh_flag_bypasses_a_usable_cache(tmp_path) -> None:
    _write(tmp_path, _fresh_rows(500))
    client = _CountingClient()

    _, source = load_candle_history(
        "BTCUSDT", "1h", 300, cache_dir=tmp_path, client=client, refresh=True
    )

    assert source == "fetch" and client.fetches == 1


def test_fetch_writes_the_cache_for_the_next_run(tmp_path) -> None:
    client = _CountingClient()
    load_candle_history("BTCUSDT", "1h", 300, cache_dir=tmp_path, client=client)

    rows, source = load_candle_history("BTCUSDT", "1h", 300, cache_dir=tmp_path, client=client)
    assert source == "cache" and client.fetches == 1


def test_fetch_failure_propagates(tmp_path) -> None:
    """A silent fallback to a shorter series would reintroduce thin samples."""

    class _BoomClient:
        def klines_history(self, *a, **k):
            raise RuntimeError("venue down")

    with pytest.raises(RuntimeError):
        load_candle_history("BTCUSDT", "1h", 300, cache_dir=tmp_path, client=_BoomClient())
