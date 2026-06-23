from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from config.settings import env_bool, env_str
from execution.mock_exchange import place_mock_order
from scripts.json_utils import append_json_log, now_utc_iso, save_json


def route_order(order_request: Dict[str, Any], current_price: Any = None, storage_dir: str | Path = "storage") -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    exchange_mode = env_str("EXCHANGE_MODE", "MOCK").upper()
    exchange_order_enabled = env_bool("EXCHANGE_ORDER_ENABLED", False)
    live_trading_enabled = env_bool("LIVE_TRADING_ENABLED", False)

    if live_trading_enabled:
        result = _blocked("LIVE_TRADING_BLOCKED", exchange_mode, "LIVE_TRADING_ENABLED=true is not allowed.")
    elif not exchange_order_enabled:
        result = _blocked("EXCHANGE_ORDER_DISABLED", exchange_mode, "EXCHANGE_ORDER_ENABLED=false.")
    elif exchange_mode != "MOCK":
        result = _blocked("UNSUPPORTED_EXCHANGE_MODE", exchange_mode, "Only MOCK exchange mode is supported in this version.")
    else:
        order_result = place_mock_order(order_request, current_price=current_price, storage_dir=storage_path)
        result = {
            "status": "ROUTED_TO_MOCK",
            "timestamp_utc": now_utc_iso(),
            "exchange_mode": exchange_mode,
            "exchange_order_enabled": exchange_order_enabled,
            "live_trading_enabled": live_trading_enabled,
            "order_result": order_result,
        }

    save_json(storage_path / "exchange_router_result.json", result)
    append_json_log(storage_path / "exchange_router_log.json", result)
    return result


def _blocked(status: str, exchange_mode: str, reason: str) -> Dict[str, Any]:
    return {
        "status": status,
        "timestamp_utc": now_utc_iso(),
        "exchange_mode": exchange_mode,
        "order_result": None,
        "reason": reason,
        "raw_response": {"live_order_executed": False},
    }
