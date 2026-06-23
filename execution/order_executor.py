from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import env_str
from execution.exchange_router import route_order
from execution.order_models import create_order_request
from risk.risk_manager import run_order_risk_check
from scripts.json_utils import append_json_log, now_utc_iso, save_json


def execute_order_with_risk_check(
    symbol: str,
    side: str,
    quantity: float,
    price: Optional[float] = None,
    current_price: Optional[float] = None,
    storage_dir: str | Path = "storage",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    order_request = create_order_request(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type="MARKET",
        price=price,
        reduce_only=False,
        mode=env_str("BOT_MODE", "PAPER_ONLY"),
        metadata=metadata or {},
    )
    risk_result = run_order_risk_check(order_request, storage_dir=storage_path, current_price=current_price)
    if not risk_result.get("approved"):
        result = {
            "status": "REJECTED_BY_RISK_MANAGER",
            "timestamp_utc": now_utc_iso(),
            "executed": False,
            "order_request": order_request,
            "risk_result": risk_result,
            "exchange_result": None,
            "safety": {"live_order_executed": False},
        }
    else:
        exchange_result = route_order(order_request, current_price=current_price, storage_dir=storage_path)
        executed = exchange_result.get("status") == "ROUTED_TO_MOCK"
        result = {
            "status": "MOCK_ORDER_ACCEPTED" if executed else "EXCHANGE_ROUTER_REJECTED",
            "timestamp_utc": now_utc_iso(),
            "executed": executed,
            "order_request": order_request,
            "risk_result": risk_result,
            "exchange_result": exchange_result,
            "safety": {"live_order_executed": False},
        }
    save_json(storage_path / "order_execution_result.json", result)
    append_json_log(storage_path / "order_execution_log.json", result)
    return result


def execute_market_buy_with_risk_check(symbol: str, quantity: float, current_price: float, storage_dir: str | Path = "storage") -> Dict[str, Any]:
    return execute_order_with_risk_check(symbol, "BUY", quantity, price=current_price, current_price=current_price, storage_dir=storage_dir)


def execute_market_sell_with_risk_check(symbol: str, quantity: float, current_price: float, storage_dir: str | Path = "storage") -> Dict[str, Any]:
    return execute_order_with_risk_check(symbol, "SELL", quantity, price=current_price, current_price=current_price, storage_dir=storage_dir)
