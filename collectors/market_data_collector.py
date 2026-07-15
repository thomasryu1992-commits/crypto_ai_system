from __future__ import annotations

import math
import random
from datetime import timedelta

from config.settings import (
    BINANCE_FUTURES_PUBLIC_BASE_URL,
    COINALYZE_API_KEY,
    COINALYZE_ENABLED,
    MARKET_DATA_PATH,
    REAL_MARKET_DATA_ENABLED,
    SYMBOL,
    TIMEFRAME,
)
from core.json_io import atomic_write_json
from core.time_utils import utc_now, utc_now_iso
from core.event_log import log_event


def _fallback_candles(count: int = 120) -> list[dict]:
    now = utc_now().replace(minute=0, second=0, microsecond=0)
    base = 100000.0
    candles = []
    for i in range(count):
        ts = now - timedelta(hours=count - i)
        drift = math.sin(i / 9) * 850 + i * 6
        close = base + drift
        open_price = close - math.sin(i / 4) * 180
        high = max(open_price, close) + 120
        low = min(open_price, close) - 120
        volume = 1000 + (i % 24) * 13
        candles.append(
            {
                "timestamp": ts.isoformat(),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": round(volume, 4),
            }
        )
    return candles


def _synthetic_payload(source_reason: str) -> dict:
    return {
        "created_at": utc_now_iso(),
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "source": "synthetic_fallback",
        "source_type": "synthetic_fallback",
        "data_quality": "synthetic",
        "is_synthetic": True,
        "is_fallback": True,
        "source_reason": source_reason,
        "candles": _fallback_candles(),
        "derivatives": {
            "funding_rate": 0.0001,
            "open_interest": 1000000000,
            "open_interest_change_24h": 0.01,
        },
    }


def collect_market_data() -> dict:
    payload: dict
    if REAL_MARKET_DATA_ENABLED:
        # Import lazily so environments without the data client / network can
        # still fall back to synthetic without an import-time failure.
        try:
            from collectors.real_market_data import collect_real_market_data

            real = collect_real_market_data(
                SYMBOL, TIMEFRAME, base_url=BINANCE_FUTURES_PUBLIC_BASE_URL
            )
            real["created_at"] = utc_now_iso()
            payload = real
        except Exception as exc:  # noqa: BLE001 - fail open to synthetic, closed to trading
            payload = _synthetic_payload(f"real_fetch_failed: {type(exc).__name__}: {exc}")
    else:
        payload = _synthetic_payload("real_market_data_disabled")

    atomic_write_json(MARKET_DATA_PATH, payload)
    log_event(
        "market_data_collected",
        {"source_type": payload["source_type"], "data_quality": payload["data_quality"]},
    )
    return payload


def main() -> None:
    result = collect_market_data()
    print(f"Collected market data: {result['symbol']} {result['timeframe']} source={result['source_type']}")


if __name__ == "__main__":
    main()
