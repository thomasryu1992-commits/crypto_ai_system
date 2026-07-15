"""Real market data via Binance USD-M Futures public endpoints.

Read-only, no API key. Produces the same payload schema as the synthetic
collector so downstream stages are unchanged, but with ``is_synthetic=False``
so the data-health gate treats it as trade-eligible. Raises on any failure so
the caller can fall back to synthetic and mark the cycle degraded.
"""

from __future__ import annotations

from typing import Any, Callable

from core.time_utils import utc_now_iso
from crypto_ai_system.data.binance_futures_collector import BinanceFuturesPublicClient

# Optional-data status vocabulary (directive §7.2). A missing/failed optional
# metric must never be silently coerced to 0.0 and passed off as a real value.
STATUS_AVAILABLE = "available"
STATUS_MISSING = "missing"
STATUS_INVALID = "invalid"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NEUTRAL_DUE_TO_MISSING = "neutral_due_to_missing"


def _health(value: float | None, status: str, reason: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "value": value,
        "status": status,
        "source": "binance_futures_public",
        "observed_at_utc": utc_now_iso(),
    }
    if reason:
        entry["reason"] = reason
    return entry


def _optional_metric(fetch: Callable[[], Any], extract: Callable[[Any], Any]) -> tuple[float | None, str, str | None]:
    """Fetch one optional metric, distinguishing real value / missing / error.

    Returns ``(value_or_None, status, reason_or_None)``. Never raises."""
    try:
        frame = fetch()
    except Exception:  # noqa: BLE001 - best-effort enrichment
        return None, STATUS_UNAVAILABLE, "api_error"
    if frame is None or getattr(frame, "empty", True):
        return None, STATUS_MISSING, "empty_response"
    try:
        value = extract(frame)
    except Exception:  # noqa: BLE001
        return None, STATUS_INVALID, "parse_error"
    if value is None:
        return None, STATUS_MISSING, "no_value"
    try:
        return float(value), STATUS_AVAILABLE, None
    except (TypeError, ValueError):
        return None, STATUS_INVALID, "parse_error"


def _oi_change_24h(client: BinanceFuturesPublicClient, symbol: str) -> tuple[float | None, str, str | None]:
    """Real 24h open-interest change from openInterestHist (1h x 25 ~= 24h)."""
    try:
        hist = client.open_interest_hist(symbol, "1h", 25)
    except Exception:  # noqa: BLE001
        return None, STATUS_UNAVAILABLE, "api_error"
    if hist is None or getattr(hist, "empty", True) or len(hist) < 2:
        return None, STATUS_NEUTRAL_DUE_TO_MISSING, "insufficient_history"
    try:
        first = float(hist.iloc[0]["open_interest"])
        last = float(hist.iloc[-1]["open_interest"])
    except Exception:  # noqa: BLE001
        return None, STATUS_INVALID, "parse_error"
    if first <= 0:
        return None, STATUS_NEUTRAL_DUE_TO_MISSING, "zero_baseline"
    return (last - first) / first, STATUS_AVAILABLE, None

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
    # Each optional metric carries a status so a missing/failed value is never
    # mistaken for a genuine 0.0 (directive §7.2).
    funding_value, funding_status, funding_reason = _optional_metric(
        lambda: client.funding_rate(binance_symbol, 1),
        lambda f: f.iloc[-1]["funding_rate"],
    )
    oi_value, oi_status, oi_reason = _optional_metric(
        lambda: client.open_interest_now(binance_symbol),
        lambda f: f.iloc[-1]["open_interest"],
    )
    oi_change_value, oi_change_status, oi_change_reason = _oi_change_24h(client, binance_symbol)

    optional_data_health = {
        "funding_rate": _health(funding_value, funding_status, funding_reason),
        "open_interest": _health(oi_value, oi_status, oi_reason),
        "open_interest_change_24h": _health(oi_change_value, oi_change_status, oi_change_reason),
    }

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
        # Numeric fields kept for backward compat (missing -> 0.0 = neutral); the
        # accompanying optional_data_health preserves the real status.
        "derivatives": {
            "funding_rate": funding_value if funding_value is not None else 0.0,
            "open_interest": oi_value if oi_value is not None else 0.0,
            "open_interest_change_24h": oi_change_value if oi_change_value is not None else 0.0,
        },
        "optional_data_health": optional_data_health,
    }
