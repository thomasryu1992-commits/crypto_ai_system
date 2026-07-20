"""Deep candle history for backtesting, cached on disk.

A single public klines call returns at most 1500 rows — roughly two months of 1h
candles, which yields far too few trades for a strategy to clear a meaningful
trade-count gate (37 trades over 1500 bars in practice, against a directive floor
of 100). ``klines_history`` pages past that cap; this module caches the result so
repeated factory runs re-read years of candles from disk instead of re-fetching
them.

The cache is a plain JSON series per (symbol, interval), always stored oldest
first. It is reused only when it holds enough bars AND its newest bar is recent
enough to still reflect the market; otherwise it is refetched. Backtests tolerate
a few hours of staleness — they are scoring years of history — so the default
window is generous rather than chasing the live edge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_ai_system.data.binance_futures_collector import BinanceFuturesPublicClient

DEFAULT_MAX_AGE_HOURS = 6.0
_CACHE_VERSION = "candle_history.v1"


def _cache_path(cache_dir: Path, symbol: str, interval: str) -> Path:
    return cache_dir / f"{symbol}_{interval}.json"


def _newest_age_hours(rows: list[dict[str, Any]]) -> float:
    newest = pd.to_datetime(rows[-1]["timestamp"], utc=True, errors="coerce")
    if pd.isna(newest):
        return float("inf")
    return float((pd.Timestamp.now(tz="UTC") - newest).total_seconds() / 3600.0)


def _read_cache(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = payload.get("candles") if isinstance(payload, dict) else None
    return rows if isinstance(rows, list) else []


def _write_cache(path: Path, symbol: str, interval: str, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _CACHE_VERSION,
        "symbol": symbol,
        "interval": interval,
        "bars": len(rows),
        "candles": rows,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def load_candle_history(
    symbol: str,
    interval: str,
    bars: int,
    *,
    cache_dir: Path,
    base_url: str = "https://fapi.binance.com",
    refresh: bool = False,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    client: BinanceFuturesPublicClient | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return ``(candles, source)`` with the newest ``bars`` rows, oldest first.

    ``source`` is "cache" or "fetch", for the caller to report. Raises whatever
    the client raises when a fetch is required and fails — a silent fallback to a
    shorter series would quietly reintroduce the thin-sample problem this module
    exists to solve.
    """
    path = _cache_path(cache_dir, symbol, interval)

    if not refresh and path.exists():
        cached = _read_cache(path)
        if len(cached) >= bars and _newest_age_hours(cached) <= max_age_hours:
            return cached[-bars:], "cache"

    client = client or BinanceFuturesPublicClient(base_url=base_url)
    frame = client.klines_history(symbol, interval, bars)
    rows = frame.to_dict("records") if not frame.empty else []
    if rows:
        _write_cache(path, symbol, interval, rows)
    return rows, "fetch"


# Funding is charged every 8h; a cache newer than one funding period + slack is
# current for any backtest or runtime evaluation.
FUNDING_MAX_AGE_HOURS = 9.0


def load_funding_history(
    symbol: str,
    records: int,
    *,
    cache_dir: Path,
    base_url: str = "https://fapi.binance.com",
    refresh: bool = False,
    max_age_hours: float = FUNDING_MAX_AGE_HOURS,
    client: BinanceFuturesPublicClient | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return ``(funding_events, source)``, newest ``records`` rows, oldest first.

    Same shape and cache discipline as ``load_candle_history``; the series is the
    venue's 8h funding events (``timestamp`` = fundingTime, ``funding_rate``).
    Raises on a required fetch failing — the caller decides how to fail closed.
    """
    path = _cache_path(cache_dir, symbol, "funding")

    if not refresh and path.exists():
        cached = _read_cache(path)
        if len(cached) >= records and _newest_age_hours(cached) <= max_age_hours:
            return cached[-records:], "cache"

    client = client or BinanceFuturesPublicClient(base_url=base_url)
    frame = client.funding_rate_history(symbol, records)
    rows = frame.to_dict("records") if not frame.empty else []
    if rows:
        _write_cache(path, symbol, "funding", rows)
    return rows, "fetch"


# Daily liquidation buckets close at UTC midnight; one period + slack keeps the
# cache current without refetching on every factory run.
LIQUIDATION_MAX_AGE_HOURS = 26.0


def _drop_unclosed_daily_bucket(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the last row if its daily bucket has not closed yet.

    Coinalyze returns the in-progress day as the newest row. A partial-day
    aggregate would make live rows see a value the backtest never scored (the
    same hazard ``drop_forming_bar`` handles for candles), so it is dropped at
    the source and every consumer sees only closed days.
    """
    if not rows:
        return rows
    newest = pd.to_datetime(rows[-1].get("timestamp"), utc=True, errors="coerce")
    if pd.isna(newest):
        return rows
    if newest + pd.Timedelta(1, unit="D") > pd.Timestamp.now(tz="UTC"):
        return rows[:-1]
    return rows


def load_liquidation_history(
    symbol: str,
    days: int,
    *,
    cache_dir: Path,
    refresh: bool = False,
    max_age_hours: float = LIQUIDATION_MAX_AGE_HOURS,
    client: Any | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return ``(liquidation_days, source)``, newest ``days`` closed rows, oldest first.

    Same shape and cache discipline as ``load_funding_history``; the series is
    Coinalyze's daily long/short liquidation aggregate for the Binance perp
    (``timestamp`` = day open UTC, ``long_liquidation`` / ``short_liquidation``).
    The still-forming current day is dropped. Raises on a required fetch failing
    (including a missing COINALYZE_API_KEY) — the caller decides how to fail
    closed.
    """
    path = _cache_path(cache_dir, symbol, "liquidation")

    if not refresh and path.exists():
        cached = _drop_unclosed_daily_bucket(_read_cache(path))
        # Freshness is measured against the last *closed* day, which is always
        # at least a day old — hence the 26h window, not candle-style hours.
        if len(cached) >= days and _newest_age_hours(cached) <= max_age_hours + 24.0:
            return cached[-days:], "cache"

    from crypto_ai_system.data.coinalyze_client import CoinalyzeClient, to_coinalyze_symbol

    client = client or CoinalyzeClient()
    coinalyze_symbol = to_coinalyze_symbol(symbol)
    now = int(pd.Timestamp.now(tz="UTC").timestamp())
    frame = client.get_liquidation_history(
        coinalyze_symbol, interval="daily", limit=days,
        from_ts=now - (days + 2) * 86400, to_ts=now,
    )
    rows = frame.to_dict("records") if not frame.empty else []
    rows = _drop_unclosed_daily_bucket(rows)
    if rows:
        _write_cache(path, symbol, "liquidation", rows)
    return rows[-days:], "fetch"
