from __future__ import annotations

from config.settings import storage_path
from core.json_io import read_json, write_json
from core.time_utils import utc_now_iso


def build_market_context() -> dict:
    snapshot = read_json(storage_path("market_snapshot.json"), default={})
    data = read_json(storage_path("coinalyze_market_data.json"), default={}).get("market_data", {})

    context = {
        "name": "MARKET_CONTEXT_BUILDER",
        "status": "CONTEXT_CREATED",
        "symbol": data.get("symbol", "BTCUSDT_PERP.A"),
        "current_price": snapshot.get("current_price", data.get("current_price")),
        "market_bias": snapshot.get("market_bias", "neutral"),
        "funding_state": "positive" if float(data.get("funding_rate_pct", 0) or 0) > 0 else "negative_or_flat",
        "oi_state": "decreasing" if float(data.get("open_interest_change_24h_pct", 0) or 0) < 0 else "increasing_or_flat",
        "spot_cvd_bias": data.get("spot_cvd_bias", "neutral"),
        "perp_cvd_bias": data.get("perp_cvd_bias", "neutral"),
        "scenario_inputs": {
            "trend": snapshot.get("market_bias", "neutral"),
            "risk": snapshot.get("liquidation_risk_zone", "neutral"),
            "funding": data.get("funding_rate_pct", 0),
            "open_interest_change": data.get("open_interest_change_24h_pct", 0),
        },
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("market_context.json"), context)
    return context
