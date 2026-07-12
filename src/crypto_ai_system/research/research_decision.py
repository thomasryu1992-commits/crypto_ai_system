from __future__ import annotations

from pathlib import Path

from config.settings import STORAGE_DIR
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso


RESEARCH_DECISION_LEGACY_V1_MODE = "RESEARCH_DECISION_ONLY_LEGACY_V1"
TRADING_EXECUTION_ENABLED_BY_THIS_MODULE = False
ORDER_ROUTING_ENABLED_BY_THIS_MODULE = False


def storage_path(relative_path: str | Path) -> Path:
    """Backward-compatible storage path helper for legacy v1 decision outputs."""
    path = Path(relative_path)
    return path if path.is_absolute() else Path(STORAGE_DIR) / path


def write_json(path: str | Path, data: dict) -> None:
    atomic_write_json(path, data)


def make_research_decision() -> dict:
    setup = read_json(storage_path("dynamic_setup_result.json"), default={})
    cycle = read_json(storage_path("research_cycle_result.json"), default={})

    result = {
        "name": "RESEARCH_DECISION",
        "status": "RESEARCH_DECISION_CREATED",
        "research_decision_legacy_v1_mode": RESEARCH_DECISION_LEGACY_V1_MODE,
        "decision_type": setup.get("decision_type", "CONDITIONAL_WATCH"),
        "source": setup.get("source", "dynamic_setup_generator"),
        "has_conditional_setup": bool(setup.get("has_conditional_setup", True)),
        "action": "WATCH" if setup.get("decision_type") == "CONDITIONAL_WATCH" else "PAPER_SIGNAL_ONLY",
        "score": cycle.get("research_score", setup.get("score", 50)),
        "trading_execution_enabled_by_this_module": TRADING_EXECUTION_ENABLED_BY_THIS_MODULE,
        "order_routing_enabled_by_this_module": ORDER_ROUTING_ENABLED_BY_THIS_MODULE,
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("research_decision_result.json"), result)
    return result
