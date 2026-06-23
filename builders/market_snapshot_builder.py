from __future__ import annotations

from config.settings import storage_path
from core.json_io import read_json, write_json
from core.time_utils import utc_now_iso


def build_market_snapshot() -> dict:
    source = read_json(storage_path("coinalyze_market_data.json"), default={})
    data = source.get("market_data", {})
    price = float(data.get("current_price", 0) or 0)
    oi_change = float(data.get("open_interest_change_24h_pct", 0) or 0)
    funding = float(data.get("funding_rate_pct", 0) or 0)
    price_change = float(data.get("price_change_24h_pct", 0) or 0)

    if price_change > 0.5 and oi_change >= 0:
        market_bias = "bullish"
    elif price_change < -0.5 and oi_change <= 0:
        market_bias = "bearish"
    else:
        market_bias = "neutral"

    snapshot = {
        "name": "MARKET_SNAPSHOT_BUILDER",
        "status": "SNAPSHOT_CREATED",
        "current_price": price,
        "market_bias": market_bias,
        "funding_rate_pct": funding,
        "open_interest_change_24h_pct": oi_change,
        "liquidation_risk_zone": data.get("liquidation_risk_zone", "neutral"),
        "source": "coinalyze_market_data",
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("market_snapshot.json"), snapshot)
    return snapshot
