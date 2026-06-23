from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from config.settings import env_bool, env_float
from execution.order_executor import execute_order_with_risk_check
from scripts.json_utils import load_json, now_utc_iso, save_json


def run_order_executor_bridge(
    paper_watch_result: Dict[str, Any],
    paper_position_result: Dict[str, Any],
    market_context: Dict[str, Any],
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    result_path = storage_path / "order_executor_bridge_result.json"
    execution_map_path = storage_path / "paper_order_execution_map.json"

    enabled = env_bool("ORDER_EXECUTOR_INTEGRATION_ENABLED", False)
    if not enabled:
        result = _base("SKIPPED", False, "ORDER_EXECUTOR_INTEGRATION_ENABLED=false.")
        save_json(result_path, result)
        return result

    events = paper_position_result.get("events", []) if isinstance(paper_position_result, dict) else []
    open_events = [e for e in events if isinstance(e, dict) and e.get("event") == "POSITION_OPENED"]
    if not open_events:
        result = _base("NO_POSITION_OPEN_EVENT", True, "No new paper position open event.")
        result["open_event_count"] = 0
        save_json(result_path, result)
        return result

    execution_map = load_json(execution_map_path, default={})
    if not isinstance(execution_map, dict):
        execution_map = {}

    bridge_events: List[Dict[str, Any]] = []
    executions: List[Dict[str, Any]] = []
    quantity = env_float("ORDER_EXECUTOR_QUANTITY", 0.00005)

    for event in open_events:
        position_id = str(event.get("position_id"))
        if position_id in execution_map:
            bridge_events.append({"event": "DUPLICATE_SKIPPED", "position_id": position_id})
            continue
        direction = str(event.get("direction", "long")).lower()
        side = "BUY" if direction == "long" else "SELL"
        order_result = execute_order_with_risk_check(
            symbol=str(event.get("symbol") or market_context.get("symbol") or "BTCUSDT"),
            side=side,
            quantity=quantity,
            price=event.get("entry_price") or market_context.get("current_price"),
            current_price=market_context.get("current_price"),
            storage_dir=storage_path,
            metadata={
                "source": "trading_bot.order_executor_bridge",
                "position_id": position_id,
                "watch_id": event.get("watch_id"),
                "setup_type": event.get("setup_type"),
            },
        )
        execution_map[position_id] = {
            "timestamp_utc": now_utc_iso(),
            "position_id": position_id,
            "status": order_result.get("status"),
            "executed": order_result.get("executed"),
            "request_id": order_result.get("order_request", {}).get("request_id") if isinstance(order_result.get("order_request"), dict) else None,
        }
        bridge_events.append({"event": "ORDER_EXECUTOR_CALLED", "position_id": position_id, "status": order_result.get("status")})
        executions.append(order_result)

    save_json(execution_map_path, execution_map)
    status = executions[-1].get("status") if executions else "DUPLICATE_SKIPPED"
    result = {
        "step": "ORDER_EXECUTOR_BRIDGE",
        "timestamp_utc": now_utc_iso(),
        "status": status,
        "enabled": True,
        "reason": None if executions else "No new execution because all events were duplicates.",
        "open_event_count": len(open_events),
        "bridge_event_count": len(bridge_events),
        "order_execution_count": len(executions),
        "events": bridge_events,
        "executions": executions,
    }
    save_json(result_path, result)
    return result


def _base(status: str, enabled: bool, reason: str) -> Dict[str, Any]:
    return {
        "step": "ORDER_EXECUTOR_BRIDGE",
        "timestamp_utc": now_utc_iso(),
        "status": status,
        "enabled": enabled,
        "reason": reason,
        "open_event_count": 0,
        "bridge_event_count": 0,
        "order_execution_count": 0,
        "events": [],
        "executions": [],
    }
