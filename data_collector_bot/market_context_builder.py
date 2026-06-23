from __future__ import annotations

from typing import Any, Dict, Optional

from config.settings import STORAGE_DIR, env_bool, env_float, env_str
from data_collector_bot.coinalyze_client import get_coinalyze_status
from scripts.json_utils import load_json, now_utc_iso, to_float


MARKET_CONTEXT_PATH = STORAGE_DIR / "market_context.json"


def build_market_context() -> Dict[str, Any]:
    """
    Step 54:
    Safe Market Context Builder

    Priority:
    1. Reuse existing storage/market_context.json if it already has current_price.
       This is normally created by knowledge_engine.market_snapshot_builder from real data.
    2. If ALLOW_SYNTHETIC_MARKET_CONTEXT=true, create a synthetic test context.
    3. Otherwise return an ERROR result without silently using a fake default price.

    Important:
    - Legacy fixed current price keys are intentionally no longer used.
    - SYNTHETIC_CURRENT_PRICE is test-only and disabled by default.
    """

    existing_context = load_json(MARKET_CONTEXT_PATH, default={})

    if isinstance(existing_context, dict):
        existing_price = to_float(existing_context.get("current_price"))

        if existing_price is not None:
            existing_context["current_price"] = existing_price
            existing_context.setdefault("timestamp_utc", now_utc_iso())
            existing_context.setdefault("symbol", env_str("SYMBOL", "BTCUSDT"))
            existing_context.setdefault("source", "existing_market_context")
            existing_context.setdefault("data_mode", "real_or_prepared")
            return existing_context

    allow_synthetic = env_bool("ALLOW_SYNTHETIC_MARKET_CONTEXT", False)

    if allow_synthetic:
        symbol = env_str("SYMBOL", "BTCUSDT")
        current_price = env_float("SYNTHETIC_CURRENT_PRICE", 106850.0)

        return {
            "timestamp_utc": now_utc_iso(),
            "symbol": symbol,
            "current_price": current_price,
            "price": current_price,
            "source": "synthetic_market_context",
            "data_mode": "synthetic_test_only",
            "market": {
                "trend": "neutral_to_bullish",
                "volatility_regime": "medium",
                "liquidity_condition": "watch_breakout_reclaim",
            },
            "derivatives": {
                "open_interest_signal": "elevated",
                "funding_rate_signal": "neutral_to_slightly_positive",
                "liquidation_cluster_above": True,
                "liquidation_cluster_below": True,
                "source_status": get_coinalyze_status(),
            },
            "onchain": {
                "exchange_flow_signal": "neutral",
                "whale_flow_signal": "neutral",
            },
            "spot": {
                "cvd_signal": "needs_confirmation",
                "volume_signal": "neutral",
            },
            "risk": {
                "macro_risk": "medium",
                "overheated_funding": False,
            },
            "warnings": [
                "Synthetic market context is enabled. Do not use this mode for live operation."
            ],
        }

    return {
        "timestamp_utc": now_utc_iso(),
        "symbol": env_str("SYMBOL", "BTCUSDT"),
        "current_price": None,
        "source": "market_context_builder",
        "data_mode": "missing_market_data",
        "status": "ERROR",
        "error_type": "MissingMarketPrice",
        "error_message": (
            "No current_price found in storage/market_context.json. "
            "Run real_market_data_collector + market_snapshot_builder, "
            "or set ALLOW_SYNTHETIC_MARKET_CONTEXT=true for local tests only."
        ),
        "derivatives": {
            "source_status": get_coinalyze_status(),
        },
    }
