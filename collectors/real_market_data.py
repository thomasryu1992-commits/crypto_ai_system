"""Real market data via Binance USD-M Futures public endpoints.

Read-only, no API key. Produces the same payload schema as the synthetic
collector so downstream stages are unchanged, but with ``is_synthetic=False``
so the data-health gate treats it as trade-eligible. Raises on any failure so
the caller can fall back to synthetic and mark the cycle degraded.
"""

from __future__ import annotations

from typing import Any

from crypto_ai_system.data.binance_futures_collector import BinanceFuturesPublicClient

# Canonical timeframe (ISO-8601 duration) -> Binance interval.
_TIMEFRAME_MAP = {
    "PT1M": "1m",
    "PT3M": "3m",
    "PT5M": "5m",
    "PT15M": "15m",
    "PT30M": "30m",
    "PT1H": "1h",
    "PT2H": "2h",
    "PT4H": "4h",
    "PT6H": "6h",
    "PT8H": "8h",
    "PT12H": "12h",
    "P1D": "1d",
}


def to_binance_symbol(symbol: str) -> str:
    """Map a canonical symbol (e.g. ``BTC-PERP``) to Binance (``BTCUSDT``)."""
    s = symbol.upper().strip().replace("/", "").replace("-", "")
    if s.endswith("USDT"):
        return s
    # Strip a contract/quote suffix, then append the Binance USDT quote.
    for suffix in ("PERP", "USDC", "USD"):
        if s.endswith(suffix) and s != suffix:
            s = s[: -len(suffix)]
            break
    return f"{s}USDT"


def to_binance_interval(timeframe: str) -> str:
    return _TIMEFRAME_MAP.get(timeframe.upper().strip(), "1h")


def _latest_float(frame: Any, column: str, default: float) -> float:
    if frame is None or getattr(frame, "empty", True):
        return default
    if column not in frame.columns:
        return default
    value = frame.iloc[-1][column]
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def collect_real_market_data(
    symbol: str,
    timeframe: str,
    *,
    base_url: str = "https://fapi.binance.com",
    limit: int = 200,
) -> dict:
    """Fetch real candles + derivatives. Raises on failure (caller falls back)."""
    binance_symbol = to_binance_symbol(symbol)
    interval = to_binance_interval(timeframe)

    client = BinanceFuturesPublicClient(base_url=base_url)

    klines = client.klines(binance_symbol, interval, limit)
    if klines is None or klines.empty:
        raise RuntimeError(f"no klines returned for {binance_symbol} {interval}")

    candles = [
        {
            "timestamp": row["timestamp"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in klines.iterrows()
    ]

    # Derivatives are best-effort; a failure here should not void real candles.
    funding_rate = 0.0
    open_interest = 0.0
    try:
        funding_rate = _latest_float(
            client.funding_rate(binance_symbol, 1), "funding_rate", 0.0
        )
    except Exception:  # noqa: BLE001 - best-effort enrichment
        pass
    try:
        open_interest = _latest_float(
            client.open_interest_now(binance_symbol), "open_interest", 0.0
        )
    except Exception:  # noqa: BLE001 - best-effort enrichment
        pass

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "binance_symbol": binance_symbol,
        "binance_interval": interval,
        "source": "binance_futures_public",
        "source_type": "binance_futures_public",
        "data_quality": "real",
        "is_synthetic": False,
        "is_fallback": False,
        "source_reason": "binance_usdm_futures_public_klines",
        "candles": candles,
        "derivatives": {
            "funding_rate": funding_rate,
            "open_interest": open_interest,
            "open_interest_change_24h": 0.0,
        },
    }
