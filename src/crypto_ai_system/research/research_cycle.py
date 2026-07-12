from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from config.settings import STORAGE_DIR
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso


RESEARCH_CYCLE_MODE = "RESEARCH_REPORT_ONLY_LEGACY_V1"
TRADING_EXECUTION_ENABLED_BY_THIS_MODULE = False
ORDER_ROUTING_ENABLED_BY_THIS_MODULE = False


def compact_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def storage_path(relative_path: str | Path) -> Path:
    """Backward-compatible storage path helper for legacy v1 research outputs."""
    path = Path(relative_path)
    return path if path.is_absolute() else Path(STORAGE_DIR) / path


def write_json(path: str | Path, data: dict) -> None:
    atomic_write_json(path, data)


def run_research_cycle() -> dict:
    setup = read_json(storage_path("dynamic_setup_result.json"), default={})
    context = read_json(storage_path("market_context.json"), default={})

    result = {
        "name": "RESEARCH_CYCLE",
        "status": "RESEARCH_CYCLE_COMPLETED",
        "research_cycle_mode": RESEARCH_CYCLE_MODE,
        "report_date": compact_date(),
        "current_price": context.get("current_price"),
        "market_bias": context.get("market_bias", "neutral"),
        "research_score": setup.get("score", 50),
        "summary": {
            "base_case": setup.get("primary_scenario", "conditional_watch"),
            "key_reason": "Market structure requires confirmation before directional execution.",
            "risk_note": "Paper mode only; no live order execution.",
        },
        "trading_execution_enabled_by_this_module": TRADING_EXECUTION_ENABLED_BY_THIS_MODULE,
        "order_routing_enabled_by_this_module": ORDER_ROUTING_ENABLED_BY_THIS_MODULE,
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("research_cycle_result.json"), result)
    write_json(storage_path(f"reports/daily_report_{compact_date()}.json"), result)
    return result
