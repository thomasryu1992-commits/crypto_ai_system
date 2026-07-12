from __future__ import annotations


def classify_scenario(final_score: float) -> str:
    if final_score >= 70:
        return "Bullish"
    if final_score >= 55:
        return "Constructive"
    if final_score >= 45:
        return "Neutral"
    if final_score >= 30:
        return "Cautious"
    return "Bearish"


def classify_quality(final_score: float, risks: list[str]) -> str:
    if "synthetic_or_fallback_data_source" in risks:
        return "D"
    if final_score >= 75:
        return "A"
    if final_score >= 60:
        return "B"
    if final_score >= 45:
        return "C"
    if final_score >= 30:
        return "D"
    return "F"


def classify_timing(final_score: float, scenario: str, risks: list[str]) -> str:
    if "synthetic_or_fallback_data_source" in risks:
        return "Data-Blocked"
    if scenario in {"Bullish", "Constructive"} and final_score < 75:
        return "Early"
    if scenario in {"Bullish", "Constructive"}:
        return "Confirmed"
    if scenario == "Neutral":
        return "Neutral"
    if scenario == "Cautious":
        return "Risk-Off"
    return "Bearish"
