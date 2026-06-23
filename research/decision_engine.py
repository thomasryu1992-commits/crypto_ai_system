from __future__ import annotations

from config.settings import RESEARCH_DECISION_PATH, RESEARCH_RESULT_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


def run_research_decision() -> dict:
    research = read_json(RESEARCH_RESULT_PATH, {})
    if not research:
        raise RuntimeError("No research result found.")

    scenario = research.get("scenario")
    timing = research.get("signal_timing")
    score = float(research.get("scores", {}).get("final_score", 0))

    bias = "NEUTRAL"
    if scenario in {"Bullish", "Constructive"} and timing not in {"Data-Blocked", "Late"}:
        bias = "ALLOW_LONG_BIAS"
    elif scenario in {"Bearish", "Cautious"}:
        bias = "ALLOW_SHORT_OR_RISK_OFF"

    decision = {
        "created_at": utc_now_iso(),
        "research_bias": bias,
        "scenario": scenario,
        "signal_quality": research.get("signal_quality"),
        "signal_timing": timing,
        "final_score": score,
        "allow_long": bias == "ALLOW_LONG_BIAS",
        "allow_short": bias == "ALLOW_SHORT_OR_RISK_OFF" and scenario == "Bearish",
        "reasons": research.get("scores", {}).get("positives", []) + research.get("scores", {}).get("risks", []),
    }
    atomic_write_json(RESEARCH_DECISION_PATH, decision)
    log_event("research_decision_created", {"research_bias": bias})
    return decision


def main() -> None:
    decision = run_research_decision()
    print(f"Research decision: {decision['research_bias']}")


if __name__ == "__main__":
    main()
