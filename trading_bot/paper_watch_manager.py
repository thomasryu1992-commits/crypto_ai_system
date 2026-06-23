from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.json_utils import load_json, now_utc_iso, save_json, to_float


def run_paper_watch_update(
    research_decision: Dict[str, Any],
    market_context: Dict[str, Any],
    setup_gate_result: Dict[str, Any],
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    watchlist_path = storage_path / "paper_watchlist.json"
    result_path = storage_path / "paper_watch_result.json"
    watchlist = load_json(watchlist_path, default=[])
    if not isinstance(watchlist, list):
        watchlist = []

    current_price = to_float(market_context.get("current_price"))
    events: List[Dict[str, Any]] = []

    for watch in watchlist:
        if isinstance(watch, dict) and watch.get("status") == "ACTIVE":
            event = _evaluate_watch(watch, current_price)
            if event:
                events.append(event)

    active_exists = any(isinstance(w, dict) and w.get("status") == "ACTIVE" for w in watchlist)
    gate_allowed = bool(setup_gate_result.get("allowed_to_create_watch", True))
    open_position_exists = _open_position_exists(storage_path)

    # Safety rule:
    # Do not create a fresh watch while a paper position is already open.
    # Without this guard, a repeated cycle above the trigger could create a new
    # watch/position and attempt a duplicate mock order.
    existing_watch_event = len(events) > 0

    if not active_exists and not open_position_exists and not existing_watch_event and gate_allowed:
        setup = research_decision.get("conditional_setup", {}) if isinstance(research_decision, dict) else {}
        if isinstance(setup, dict) and setup:
            watch = _create_watch(research_decision, setup)
            watchlist.append(watch)
            events.append({"event": "PAPER_WATCH_CREATED", "watch_id": watch.get("watch_id"), "setup_type": watch.get("setup_type")})

    save_json(watchlist_path, watchlist)
    result = {
        "status": _resolve_status(events),
        "timestamp_utc": now_utc_iso(),
        "events": events,
        "watchlist": watchlist,
        "summary": _summary(watchlist),
    }
    save_json(result_path, result)
    return result


def _open_position_exists(storage_path: Path) -> bool:
    positions = load_json(storage_path / "paper_positions.json", default=[])
    if not isinstance(positions, list):
        return False
    return any(isinstance(item, dict) and item.get("status") == "OPEN" for item in positions)


def _create_watch(research_decision: Dict[str, Any], setup: Dict[str, Any]) -> Dict[str, Any]:
    now = now_utc_iso()
    return {
        "watch_id": f"watch_{uuid.uuid4().hex[:12]}",
        "symbol": research_decision.get("symbol", "BTCUSDT"),
        "setup_type": setup.get("setup_type", "unknown"),
        "direction": str(setup.get("direction", "long")).lower(),
        "trigger_price": to_float(setup.get("trigger_price")),
        "invalidation_price": to_float(setup.get("invalidation_price")),
        "take_profit": to_float(setup.get("take_profit")),
        "expires_after_hours": setup.get("expires_after_hours", 24),
        "status": "ACTIVE",
        "created_at_utc": now,
        "updated_at_utc": now,
        "source_report": research_decision.get("source_report"),
        "active_scenario": research_decision.get("active_scenario"),
        "kb_lint_status": research_decision.get("kb_lint_status"),
    }


def _evaluate_watch(watch: Dict[str, Any], current_price: float | None) -> Dict[str, Any] | None:
    if current_price is None:
        return None
    direction = str(watch.get("direction", "long")).lower()
    trigger = to_float(watch.get("trigger_price"))
    invalidation = to_float(watch.get("invalidation_price"))
    if trigger is None or invalidation is None:
        return None

    if direction == "long":
        if current_price >= trigger:
            watch["status"] = "TRIGGERED"
            watch["triggered_at_utc"] = now_utc_iso()
            watch["updated_at_utc"] = now_utc_iso()
            return {"event": "PAPER_WATCH_TRIGGERED", "watch_id": watch.get("watch_id"), "current_price": current_price}
        if current_price <= invalidation:
            watch["status"] = "INVALIDATED"
            watch["invalidated_at_utc"] = now_utc_iso()
            watch["updated_at_utc"] = now_utc_iso()
            return {"event": "PAPER_WATCH_INVALIDATED", "watch_id": watch.get("watch_id"), "current_price": current_price}
    else:
        if current_price <= trigger:
            watch["status"] = "TRIGGERED"
            watch["triggered_at_utc"] = now_utc_iso()
            watch["updated_at_utc"] = now_utc_iso()
            return {"event": "PAPER_WATCH_TRIGGERED", "watch_id": watch.get("watch_id"), "current_price": current_price}
        if current_price >= invalidation:
            watch["status"] = "INVALIDATED"
            watch["invalidated_at_utc"] = now_utc_iso()
            watch["updated_at_utc"] = now_utc_iso()
            return {"event": "PAPER_WATCH_INVALIDATED", "watch_id": watch.get("watch_id"), "current_price": current_price}
    return None


def _summary(watchlist: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "active_watch_count": sum(1 for w in watchlist if isinstance(w, dict) and w.get("status") == "ACTIVE"),
        "triggered_watch_count": sum(1 for w in watchlist if isinstance(w, dict) and w.get("status") == "TRIGGERED"),
        "invalidated_watch_count": sum(1 for w in watchlist if isinstance(w, dict) and w.get("status") == "INVALIDATED"),
        "expired_watch_count": sum(1 for w in watchlist if isinstance(w, dict) and w.get("status") == "EXPIRED"),
    }


def _resolve_status(events: List[Dict[str, Any]]) -> str:
    names = [e.get("event") for e in events]
    if "PAPER_WATCH_TRIGGERED" in names:
        return "PAPER_WATCH_TRIGGERED"
    if "PAPER_WATCH_CREATED" in names:
        return "PAPER_WATCH_CREATED"
    if "PAPER_WATCH_INVALIDATED" in names:
        return "PAPER_WATCH_INVALIDATED"
    return "NO_WATCH_EVENT"
