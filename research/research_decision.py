from __future__ import annotations

from config.settings import storage_path
from core.json_io import read_json, write_json
from core.time_utils import utc_now_iso


def make_research_decision() -> dict:
    setup = read_json(storage_path("dynamic_setup_result.json"), default={})
    cycle = read_json(storage_path("research_cycle_result.json"), default={})

    result = {
        "name": "RESEARCH_DECISION",
        "status": "RESEARCH_DECISION_CREATED",
        "decision_type": setup.get("decision_type", "CONDITIONAL_WATCH"),
        "source": setup.get("source", "dynamic_setup_generator"),
        "has_conditional_setup": bool(setup.get("has_conditional_setup", True)),
        "action": "WATCH" if setup.get("decision_type") == "CONDITIONAL_WATCH" else "PAPER_SIGNAL_ONLY",
        "score": cycle.get("research_score", setup.get("score", 50)),
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("research_decision_result.json"), result)
    return result
