from __future__ import annotations

from pathlib import Path

from config.settings import STORAGE_DIR
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso


DYNAMIC_SETUP_MODE = "RESEARCH_ONLY_LEGACY_V1"
TRADING_EXECUTION_ENABLED_BY_THIS_MODULE = False
ORDER_ROUTING_ENABLED_BY_THIS_MODULE = False


def storage_path(relative_path: str | Path) -> Path:
    """Backward-compatible storage path helper for legacy v1 research outputs."""
    path = Path(relative_path)
    return path if path.is_absolute() else Path(STORAGE_DIR) / path


def write_json(path: str | Path, data: dict) -> None:
    atomic_write_json(path, data)


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
        "dynamic_setup_mode": DYNAMIC_SETUP_MODE,
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
        "trading_execution_enabled_by_this_module": TRADING_EXECUTION_ENABLED_BY_THIS_MODULE,
        "order_routing_enabled_by_this_module": ORDER_ROUTING_ENABLED_BY_THIS_MODULE,
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("dynamic_setup_result.json"), result)
    return result
