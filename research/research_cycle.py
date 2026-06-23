from __future__ import annotations

from config.settings import storage_path
from core.json_io import read_json, write_json
from core.time_utils import compact_date, utc_now_iso


def run_research_cycle() -> dict:
    setup = read_json(storage_path("dynamic_setup_result.json"), default={})
    context = read_json(storage_path("market_context.json"), default={})

    result = {
        "name": "RESEARCH_CYCLE",
        "status": "RESEARCH_CYCLE_COMPLETED",
        "report_date": compact_date(),
        "current_price": context.get("current_price"),
        "market_bias": context.get("market_bias", "neutral"),
        "research_score": setup.get("score", 50),
        "summary": {
            "base_case": setup.get("primary_scenario", "conditional_watch"),
            "key_reason": "Market structure requires confirmation before directional execution.",
            "risk_note": "Paper mode only; no live order execution.",
        },
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("research_cycle_result.json"), result)
    write_json(storage_path(f"reports/daily_report_{compact_date()}.json"), result)
    return result
