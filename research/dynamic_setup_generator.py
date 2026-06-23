from __future__ import annotations

from config.settings import storage_path
from core.json_io import read_json, write_json
from core.time_utils import utc_now_iso


def generate_dynamic_setup() -> dict:
    context = read_json(storage_path("market_context.json"), default={})
    bias = context.get("market_bias", "neutral")
    funding_state = context.get("funding_state", "positive")
    oi_state = context.get("oi_state", "decreasing")

    score = 50
    score += 10 if bias == "bullish" else -10 if bias == "bearish" else 0
    score -= 5 if funding_state == "positive" and oi_state == "decreasing" else 0

    if score >= 60:
        primary_scenario = "bullish_continuation"
    elif score <= 40:
        primary_scenario = "bearish_pressure"
    else:
        primary_scenario = "conditional_watch"

    result = {
        "name": "DYNAMIC_SETUP_GENERATOR",
        "status": "DYNAMIC_SETUP_CREATED",
        "has_conditional_setup": True,
        "decision_type": "CONDITIONAL_WATCH" if primary_scenario == "conditional_watch" else "DIRECTIONAL_SETUP",
        "source": "dynamic_setup_generator",
        "score": score,
        "primary_scenario": primary_scenario,
        "conditions": [
            "Confirm 1H close direction before entry",
            "Avoid real order execution while TRADING_MODE=paper",
            "Use OI/funding/CVD confirmation before signal escalation",
        ],
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("dynamic_setup_result.json"), result)
    return result
