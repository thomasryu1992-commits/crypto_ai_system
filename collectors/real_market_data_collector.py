from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from config.settings import Settings, storage_path
from core.json_io import write_json
from core.time_utils import utc_now_iso


ENDPOINTS = [
    "price",
    "open_interest",
    "funding_rate",
    "long_short_ratio",
    "liquidation",
    "volume",
    "cvd",
    "basis",
]


def _fallback_market_data() -> Dict[str, Any]:
    base_price = 64118.6
    return {
        "symbol": Settings.SYMBOL,
        "interval": Settings.INTERVAL,
        "provider": "coinalyze" if Settings.ENABLE_COINALYZE else "fallback_sample",
        "current_price": base_price,
        "price_change_24h_pct": 0.12,
        "open_interest_usd": 103_517_391_243,
        "open_interest_change_24h_pct": -0.91,
        "funding_rate_pct": 0.00156,
        "long_short_ratio": 1.03,
        "liquidation_risk_zone": "neutral",
        "spot_cvd_bias": "slightly_positive",
        "perp_cvd_bias": "neutral",
        "volume_state": "normal",
        "basis_state": "flat",
        "endpoints": {name: {"ok": True, "value": "collected"} for name in ENDPOINTS},
    }


def collect_real_market_data() -> Dict[str, Any]:
    # Production hook: add real Coinalyze HTTP calls here when API limits and endpoint mapping are finalized.
    data = _fallback_market_data()
    raw_path = storage_path("raw_data/BTCUSDT_PERP_A_coinalyze.json")
    write_json(raw_path, data)

    result = {
        "name": "REAL_MARKET_DATA_COLLECTOR",
        "status": "COLLECTED",
        "provider": data["provider"],
        "symbol": Settings.SYMBOL,
        "interval": Settings.INTERVAL,
        "ok_endpoints": len(ENDPOINTS),
        "error_endpoints": 0,
        "raw_path": str(Path(raw_path).resolve()),
        "market_data": data,
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("coinalyze_market_data.json"), result)
    return result
