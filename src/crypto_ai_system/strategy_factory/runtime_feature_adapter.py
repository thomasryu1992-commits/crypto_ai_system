"""Bridge the runtime candle stream to the strategy feature contract.

Strategies are written against the ``feature_store`` columns (rsi, adx, atr,
market_regime, moving averages …), but the lean runtime pipeline only persists a
small ``market_snapshot``. This adapter rebuilds the *full* feature row from the
runtime OHLCV candles using the same ``build_feature_frame`` the backtest uses,
so the router sees exactly the features a strategy was validated against — one
feature source for backtest and live.

Multi-timeframe context and optional-data collectors are disabled here: the
router needs the price/indicator/regime columns, not the heavy auxiliary feeds,
and disabling them keeps this fast and side-effect-free. Funding and daily
liquidations are the exceptions: their real event series (deep-history caches)
are aligned onto every frame, so funding_rate / funding_zscore and the
liquidation_* columns carry real values in backtest and live alike — and are
NaN (indeterminate), never a constant, when a series cannot be loaded. The
remaining feed-less columns (open interest, legacy mtf, aux scores) still come
out as constant fallbacks, so a spec must not reference them — the S3 validator
rejects any that do (see
``allowed_feature_registry.RUNTIME_UNAVAILABLE_FEATURES``).
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import pandas as pd

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.features.feature_store import build_feature_frame, latest_feature_snapshot

_MIN_CANDLES = 2

_TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}

# Bars loaded for a non-base timeframe: enough for every indicator warm-up
# (ma50/ema50 = 50, atr_percentile window = 100) with head-room.
RUNTIME_HISTORY_BARS = 400


def _cfg_without_heavy_feeds(cfg: AppConfig) -> AppConfig:
    settings = dict(cfg.settings)
    settings["price_data"] = {**settings.get("price_data", {}), "include_multi_timeframe_context": False}
    return AppConfig(root=cfg.root, settings=settings)


# Funding events kept for the frame: 8h cadence -> ~3/day; 7000 covers >6 years,
# longer than any candle series we backtest.
FUNDING_HISTORY_RECORDS = 7000


def runtime_symbol() -> str:
    """The pipeline's own symbol, in venue form (e.g. BTCUSDT)."""
    import config.settings as settings
    from collectors.real_market_data import to_binance_symbol

    return to_binance_symbol(getattr(settings, "SYMBOL", "BTC-PERP"))


def _default_funding_loader(symbol: str | None = None) -> "pd.DataFrame":
    import config.settings as settings
    from crypto_ai_system.data.candle_history import load_funding_history

    rows, _ = load_funding_history(
        symbol or runtime_symbol(), FUNDING_HISTORY_RECORDS,
        cache_dir=settings.HISTORY_DIR,
        base_url=settings.BINANCE_FUTURES_PUBLIC_BASE_URL,
    )
    return pd.DataFrame(rows)


# Daily liquidation rows kept for the frame: 2300 covers the deepest candle
# series the factory backtests (2200 x 1d) with head-room.
LIQUIDATION_HISTORY_DAYS = 2300


def _default_liquidation_loader(symbol: str | None = None) -> "pd.DataFrame":
    import config.settings as settings
    from crypto_ai_system.data.candle_history import load_liquidation_history

    rows, _ = load_liquidation_history(
        symbol or runtime_symbol(), LIQUIDATION_HISTORY_DAYS,
        cache_dir=settings.HISTORY_DIR,
    )
    return pd.DataFrame(rows)


def build_backtest_frame(
    candles: Sequence[dict[str, Any]],
    *,
    cfg: AppConfig | None = None,
    funding_loader: Callable[[], "pd.DataFrame"] | None = None,
    liquidation_loader: Callable[[], "pd.DataFrame"] | None = None,
) -> "pd.DataFrame":
    """Return the full feature frame from OHLCV candles (the backtest input).

    Same feature source as the live router — the factory backtests strategies on
    exactly the columns they are evaluated against at runtime. The real 8h
    funding series and daily liquidation series are aligned onto the frame
    (funding_rate / funding_zscore, liquidation_*); if a series cannot be loaded
    its columns are NaN = indeterminate, so a spec referencing them fails closed
    to no-entry rather than evaluating a constant. Returns an empty frame when
    there are too few candles or required columns are missing.
    """
    if not candles or len(candles) < _MIN_CANDLES:
        return pd.DataFrame()
    cfg = _cfg_without_heavy_feeds(cfg or load_config("."))
    ohlcv = pd.DataFrame(list(candles))
    required = {"open", "high", "low", "close", "volume", "timestamp"}
    if not required.issubset(ohlcv.columns):
        return pd.DataFrame()
    # Candle rows are symbol-labelled; the aligned series must come from the
    # SAME symbol or rolling stats would be computed against another market.
    row_symbol = str(ohlcv.iloc[0].get("symbol") or "") or None
    try:
        funding = funding_loader() if funding_loader is not None else _default_funding_loader(row_symbol)
    except Exception:  # noqa: BLE001 - indeterminate funding, never a constant
        funding = pd.DataFrame()
    try:
        liquidations = (liquidation_loader() if liquidation_loader is not None
                        else _default_liquidation_loader(row_symbol))
    except Exception:  # noqa: BLE001 - indeterminate liquidations, never a constant
        liquidations = pd.DataFrame()
    return build_feature_frame(ohlcv, pd.DataFrame(), cfg, funding=funding, liquidations=liquidations)


def build_runtime_feature_row(
    candles: Sequence[dict[str, Any]],
    *,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    """Return the latest feature row from runtime OHLCV candles.

    ``candles`` are dicts with open/high/low/close/volume/timestamp (the runtime
    market-data candles). Returns an empty dict when there are too few candles —
    the router then produces NO_ENTRY (fail-closed).
    """
    frame = build_backtest_frame(candles, cfg=cfg)
    if frame.empty:
        return {}
    return latest_feature_snapshot(frame)


def drop_forming_bar(
    candles: Sequence[dict[str, Any]], timeframe: str, *, now: str | None = None
) -> list[dict[str, Any]]:
    """Drop the last candle if it has not finished forming yet.

    The venue returns the in-progress bar as the last row. The backtest evaluates
    only *closed* bars (signal on bar i, entry at bar i+1 open), so evaluating a
    live strategy on a half-formed daily candle would judge it on values its
    backtest never saw. An unparseable timestamp keeps the row — the evaluator's
    NaN handling stays the fail-closed backstop.
    """
    rows = list(candles)
    minutes = _TIMEFRAME_MINUTES.get(str(timeframe))
    if not rows or minutes is None:
        return rows
    last_open = pd.to_datetime(rows[-1].get("timestamp"), utc=True, errors="coerce")
    if pd.isna(last_open):
        return rows
    now_ts = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True, errors="coerce")
    if pd.isna(now_ts):
        return rows
    if last_open + pd.Timedelta(minutes, unit="min") > now_ts:
        return rows[:-1]
    return rows


def build_runtime_feature_row_for_timeframe(
    timeframe: str,
    base_candles: Sequence[dict[str, Any]],
    *,
    base_timeframe: str,
    symbol: str | None = None,
    cfg: AppConfig | None = None,
    now: str | None = None,
    history_loader: Callable[[str, int], Sequence[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Latest feature row on ``(symbol, timeframe)`` — the frame a spec was
    backtested on.

    A spec on the runtime base symbol AND base timeframe uses the pipeline's own
    candles (unchanged behavior). Anything else — another timeframe or another
    symbol — loads its own candle series from the deep-history cache and drops
    the still-forming last bar, so the row is built from exactly the kind of
    closed bars the backtest scored. Returns {} when the series cannot be built —
    the router treats that as no-entry.

    ``history_loader(timeframe, bars) -> candles`` is injectable for tests; the
    default reads the on-disk deep-history cache (network only when stale).
    """
    base_symbol = runtime_symbol()
    spec_symbol = str(symbol or base_symbol)
    if str(timeframe) == str(base_timeframe) and spec_symbol == base_symbol:
        return build_runtime_feature_row(base_candles, cfg=cfg)

    if history_loader is None:
        def history_loader(tf: str, bars: int) -> Sequence[dict[str, Any]]:
            import config.settings as settings
            from crypto_ai_system.data.candle_history import load_candle_history

            rows, _ = load_candle_history(
                spec_symbol, tf, bars,
                cache_dir=settings.HISTORY_DIR,
                base_url=settings.BINANCE_FUTURES_PUBLIC_BASE_URL,
            )
            return rows

    try:
        candles = history_loader(str(timeframe), RUNTIME_HISTORY_BARS)
    except Exception:  # noqa: BLE001 - no row -> fail closed to no-entry
        return {}
    candles = drop_forming_bar(candles, str(timeframe), now=now)
    return build_runtime_feature_row(candles, cfg=cfg)
