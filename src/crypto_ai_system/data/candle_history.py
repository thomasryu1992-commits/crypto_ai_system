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
