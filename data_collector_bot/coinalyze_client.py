from __future__ import annotations

from typing import Any, Dict

from config.settings import env_str


def get_coinalyze_status() -> Dict[str, Any]:
    api_key = env_str("COINALYZE_API_KEY", "")
    configured = bool(api_key and api_key != "your_coinalyze_api_key_here")
    return {
        "source": "coinalyze",
        "configured": configured,
        "base_url": env_str("COINALYZE_BASE_URL", "https://api.coinalyze.net/v1"),
        "symbol": env_str("COINALYZE_SYMBOL", "BTCUSDT_PERP.A"),
        "exchange": env_str("COINALYZE_EXCHANGE", "binance"),
        "note": "Live API fetching is disabled in this safe template. Add endpoint-specific fetchers after API validation.",
    }
