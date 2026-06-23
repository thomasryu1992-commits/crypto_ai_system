from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List

from scripts.json_utils import load_json, now_utc_iso, save_json, to_float


def run_paper_position_update(
    paper_watch_result: Dict[str, Any],
    market_context: Dict[str, Any],
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    positions_path = storage_path / "paper_positions.json"
    history_path = storage_path / "paper_trade_history.json"
    result_path = storage_path / "paper_position_result.json"

    positions = load_json(positions_path, default=[])
    history = load_json(history_path, default=[])
    if not isinstance(positions, list):
        positions = []
    if not isinstance(history, list):
        history = []

    current_price = to_float(market_context.get("current_price"))
    events: List[Dict[str, Any]] = []

    for position in positions:
        if isinstance(position, dict) and position.get("status") == "OPEN":
            close_event = _evaluate_position_close(position, current_price)
            if close_event:
                events.append(close_event)
                history.append(_trade_from_closed_position(position, close_event))

    watchlist = paper_watch_result.get("watchlist", [])
    if isinstance(watchlist, list):
        existing_watch_ids = {p.get("watch_id") for p in positions if isinstance(p, dict)}
        for watch in watchlist:
            if not isinstance(watch, dict):
                continue
            if watch.get("status") != "TRIGGERED":
                continue
            if watch.get("watch_id") in existing_watch_ids:
                continue
            position = _open_position_from_watch(watch, current_price)
            positions.append(position)
            events.append({
                "event": "POSITION_OPENED",
                "position_id": position.get("position_id"),
                "watch_id": position.get("watch_id"),
                "symbol": position.get("symbol"),
                "direction": position.get("direction"),
                "entry_price": position.get("entry_price"),
                "setup_type": position.get("setup_type"),
            })

    save_json(positions_path, positions)
    save_json(history_path, history)
    result = {
        "status": _resolve_status(events),
        "timestamp_utc": now_utc_iso(),
        "events": events,
        "positions": positions,
        "trade_history": history,
        "summary": _summary(positions, history),
    }
    save_json(result_path, result)
    return result


def _open_position_from_watch(watch: Dict[str, Any], current_price: float | None) -> Dict[str, Any]:
    entry = current_price if current_price is not None else to_float(watch.get("trigger_price"))
    return {
        "position_id": f"pos_{uuid.uuid4().hex[:12]}",
        "watch_id": watch.get("watch_id"),
        "symbol": watch.get("symbol", "BTCUSDT"),
        "direction": str(watch.get("direction", "long")).lower(),
        "status": "OPEN",
        "setup_type": watch.get("setup_type"),
        "entry_price": entry,
        "stop_loss": to_float(watch.get("invalidation_price")),
        "take_profit": to_float(watch.get("take_profit")),
        "opened_at_utc": now_utc_iso(),
        "source_report": watch.get("source_report"),
        "active_scenario": watch.get("active_scenario"),
    }


def _evaluate_position_close(position: Dict[str, Any], current_price: float | None) -> Dict[str, Any] | None:
    if current_price is None:
        return None
    direction = str(position.get("direction", "long")).lower()
    stop = to_float(position.get("stop_loss"))
    tp = to_float(position.get("take_profit"))
    if stop is None or tp is None:
        return None
    reason = None
    if direction == "long":
        if current_price >= tp:
            reason = "TAKE_PROFIT"
        elif current_price <= stop:
            reason = "STOP_LOSS"
    else:
        if current_price <= tp:
            reason = "TAKE_PROFIT"
        elif current_price >= stop:
            reason = "STOP_LOSS"
    if not reason:
        return None
    entry = to_float(position.get("entry_price")) or current_price
    pnl_pct = _pnl_pct(entry, current_price, direction)
    position.update({
        "status": "CLOSED",
        "closed_at_utc": now_utc_iso(),
        "exit_price": current_price,
        "close_reason": reason,
        "realized_pnl_pct": pnl_pct,
    })
    return {
        "event": "POSITION_CLOSED_TP" if reason == "TAKE_PROFIT" else "POSITION_CLOSED_SL",
        "position_id": position.get("position_id"),
        "exit_price": current_price,
        "close_reason": reason,
        "realized_pnl_pct": pnl_pct,
    }


def _pnl_pct(entry: float, exit_price: float, direction: str) -> float:
    if entry == 0:
        return 0.0
    if direction == "short":
        return round(((entry - exit_price) / entry) * 100, 6)
    return round(((exit_price - entry) / entry) * 100, 6)


def _trade_from_closed_position(position: Dict[str, Any], close_event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trade_id": f"trade_{uuid.uuid4().hex[:12]}",
        "position_id": position.get("position_id"),
        "watch_id": position.get("watch_id"),
        "symbol": position.get("symbol"),
        "direction": position.get("direction"),
        "setup_type": position.get("setup_type"),
        "entry_price": position.get("entry_price"),
        "exit_price": position.get("exit_price"),
        "close_reason": position.get("close_reason"),
        "realized_pnl_pct": position.get("realized_pnl_pct"),
        "opened_at_utc": position.get("opened_at_utc"),
        "closed_at_utc": position.get("closed_at_utc"),
    }


def _summary(positions: List[Dict[str, Any]], history: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_realized = sum(to_float(t.get("realized_pnl_pct")) or 0.0 for t in history if isinstance(t, dict))
    return {
        "open_position_count": sum(1 for p in positions if isinstance(p, dict) and p.get("status") == "OPEN"),
        "closed_position_count": sum(1 for p in positions if isinstance(p, dict) and p.get("status") == "CLOSED"),
        "trade_history_count": len(history),
        "total_realized_pnl_pct": round(total_realized, 6),
    }


def _resolve_status(events: List[Dict[str, Any]]) -> str:
    names = [e.get("event") for e in events]
    if "POSITION_OPENED" in names:
        return "PAPER_POSITION_OPENED"
    if "POSITION_CLOSED_TP" in names:
        return "PAPER_POSITION_CLOSED_TP"
    if "POSITION_CLOSED_SL" in names:
        return "PAPER_POSITION_CLOSED_SL"
    return "NO_POSITION_EVENT"
