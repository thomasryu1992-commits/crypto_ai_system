"""Bridge the runtime candle stream to the strategy feature contract.

Strategies are written against the ``feature_store`` columns (rsi, adx, atr,
market_regime, moving averages …), but the lean runtime pipeline only persists a
small ``market_snapshot``. This adapter rebuilds the *full* feature row from the
runtime OHLCV candles using the same ``build_feature_frame`` the backtest uses,
so the router sees exactly the features a strategy was validated against — one
feature source for backtest and live.

Multi-timeframe context and optional-data collectors are disabled here: the
router needs the price/indicator/regime columns, not the heavy auxiliary feeds,
and disabling them keeps this fast and side-effect-free. Derivative columns
(funding, OI change) are absent without a derivatives feed, so a strategy that
depends on them evaluates as indeterminate — fail-closed, no match.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.features.feature_store import build_feature_frame, latest_feature_snapshot

_MIN_CANDLES = 2


def _cfg_without_heavy_feeds(cfg: AppConfig) -> AppConfig:
    settings = dict(cfg.settings)
    settings["price_data"] = {**settings.get("price_data", {}), "include_multi_timeframe_context": False}
    return AppConfig(root=cfg.root, settings=settings)


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
    if not candles or len(candles) < _MIN_CANDLES:
        return {}
    cfg = _cfg_without_heavy_feeds(cfg or load_config("."))
    ohlcv = pd.DataFrame(list(candles))
    required = {"open", "high", "low", "close", "volume", "timestamp"}
    if not required.issubset(ohlcv.columns):
        return {}
    frame = build_feature_frame(ohlcv, pd.DataFrame(), cfg)
    if frame.empty:
        return {}
    return latest_feature_snapshot(frame)
