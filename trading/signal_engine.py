from __future__ import annotations

from config.settings import MARKET_SNAPSHOT_PATH, RESEARCH_RESULT_PATH
from core.json_io import read_json


def generate_trading_signal() -> dict:
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    research = read_json(RESEARCH_RESULT_PATH, {})

    signal = "NONE"
    confidence = 0
    reasons = []

    trend = snapshot.get("trend_bias")
    scenario = research.get("scenario")
    timing = research.get("signal_timing")

    if snapshot.get("is_synthetic") or snapshot.get("is_fallback"):
        return {
            "signal": "NONE",
            "confidence": 0,
            "reasons": ["synthetic_or_fallback_data_no_signal"],
        }

    if trend == "bullish" and scenario in {"Bullish", "Constructive"} and timing in {"Early", "Confirmed"}:
        signal = "LONG"
        confidence = 65
        reasons.append("trend_and_research_aligned_long")
    elif trend == "bearish" and scenario == "Bearish":
        signal = "SHORT"
        confidence = 60
        reasons.append("trend_and_research_aligned_short")

    return {"signal": signal, "confidence": confidence, "reasons": reasons}
