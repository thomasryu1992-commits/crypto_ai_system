from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from scripts.json_utils import load_json, now_utc_iso, save_json


def build_bot_state(storage_dir: str | Path = "storage") -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    watchlist = load_json(storage_path / "paper_watchlist.json", default=[])
    positions = load_json(storage_path / "paper_positions.json", default=[])
    history = load_json(storage_path / "paper_trade_history.json", default=[])
    gate = load_json(storage_path / "setup_decision_filter_result.json", default={})
    if not isinstance(watchlist, list): watchlist = []
    if not isinstance(positions, list): positions = []
    if not isinstance(history, list): history = []
    active_watch_count = sum(1 for w in watchlist if isinstance(w, dict) and w.get("status") == "ACTIVE")
    open_position_count = sum(1 for p in positions if isinstance(p, dict) and p.get("status") == "OPEN")
    has_error = False
    lifecycle = "IDLE"
    if open_position_count > 0:
        lifecycle = "POSITION_OPEN"
    elif active_watch_count > 0:
        lifecycle = "WATCH_ACTIVE"
    blocked = isinstance(gate, dict) and gate.get("status") == "BLOCKED"
    state = {
        "status": "STATE_CREATED",
        "timestamp_utc": now_utc_iso(),
        "lifecycle_state": lifecycle,
        "permissions": {
            "can_run_next_cycle": True,
            "can_create_new_watch": active_watch_count == 0 and open_position_count == 0 and not blocked,
            "can_open_new_position": open_position_count == 0,
        },
        "counts": {
            "active_watch_count": active_watch_count,
            "open_position_count": open_position_count,
            "trade_history_count": len(history),
        },
        "risk_flags": {
            "has_error": has_error,
            "has_open_position": open_position_count > 0,
            "has_active_watch": active_watch_count > 0,
            "setup_gate_blocked": blocked,
        },
    }
    save_json(storage_path / "bot_state.json", state)
    return state
