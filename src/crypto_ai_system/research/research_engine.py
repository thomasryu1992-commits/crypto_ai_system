from __future__ import annotations

from config.settings import MARKET_CONTEXT_PATH, RESEARCH_RESULT_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from crypto_ai_system.research.scoring import score_market_context
from crypto_ai_system.research.scenario import classify_quality, classify_scenario, classify_timing


RESEARCH_ENGINE_MODE = "RESEARCH_REPORT_ONLY"
TRADING_EXECUTION_ENABLED_BY_THIS_MODULE = False
ORDER_ROUTING_ENABLED_BY_THIS_MODULE = False


def run_research_cycle() -> dict:
    context = read_json(MARKET_CONTEXT_PATH, {})
    if not context:
        raise RuntimeError("No market context found. Run build_market_context first.")

    scores = score_market_context(context)
    scenario = classify_scenario(scores["final_score"])
    quality = classify_quality(scores["final_score"], scores.get("risks", []))
    timing = classify_timing(scores["final_score"], scenario, scores.get("risks", []))

    result = {
        "created_at": utc_now_iso(),
        "scenario": scenario,
        "signal_quality": quality,
        "signal_timing": timing,
        "scores": scores,
        "context_summary": context.get("summary"),
        "allow_research_bias": timing not in {"Data-Blocked", "Risk-Off", "Bearish"},
        "research_engine_mode": RESEARCH_ENGINE_MODE,
        "trading_execution_enabled_by_this_module": TRADING_EXECUTION_ENABLED_BY_THIS_MODULE,
        "order_routing_enabled_by_this_module": ORDER_ROUTING_ENABLED_BY_THIS_MODULE,
    }
    atomic_write_json(RESEARCH_RESULT_PATH, result)
    log_event("research_cycle_completed", {"scenario": scenario, "quality": quality, "timing": timing})
    return result


def main() -> None:
    result = run_research_cycle()
    print(f"Research cycle: {result['scenario']} quality={result['signal_quality']} timing={result['signal_timing']}")


if __name__ == "__main__":
    main()
