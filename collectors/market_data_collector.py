from __future__ import annotations

import math
import random
from datetime import timedelta

from config.settings import COINALYZE_API_KEY, COINALYZE_ENABLED, MARKET_DATA_PATH, SYMBOL, TIMEFRAME
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


def collect_market_data() -> dict:
    # Step130: fallback data remains useful for dry-run, but downstream health blocks trading.
    source_type = "synthetic_fallback"
    data_quality = "synthetic"
    source_reason = "coinalyze_disabled_or_missing_key"

    if COINALYZE_ENABLED and COINALYZE_API_KEY:
        # Placeholder for future real API implementation.
        # The package keeps live data disabled unless explicitly implemented and validated.
        source_type = "synthetic_fallback"
        data_quality = "synthetic"
        source_reason = "real_coinalyze_fetch_not_implemented_in_guarded_package"

    candles = _fallback_candles()
    payload = {
        "created_at": utc_now_iso(),
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "source": source_type,
        "source_type": source_type,
        "data_quality": data_quality,
        "is_synthetic": True,
        "is_fallback": True,
        "source_reason": source_reason,
        "candles": candles,
        "derivatives": {
            "funding_rate": 0.0001,
            "open_interest": 1000000000,
            "open_interest_change_24h": 0.01,
        },
    }
    atomic_write_json(MARKET_DATA_PATH, payload)
    log_event("market_data_collected", {"source_type": source_type, "data_quality": data_quality})
    return payload


def main() -> None:
    result = collect_market_data()
    print(f"Collected market data: {result['symbol']} {result['timeframe']} source={result['source_type']}")


if __name__ == "__main__":
    main()
