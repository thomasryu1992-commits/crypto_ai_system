from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from scripts.json_utils import append_json_log, now_utc_iso, save_json, to_float


def place_mock_order(order_request: Dict[str, Any], current_price: Any = None, storage_dir: str | Path = "storage") -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    filled_price = to_float(order_request.get("price")) or to_float(current_price) or 0.0
    filled_quantity = to_float(order_request.get("quantity")) or 0.0
    result = {
        "status": "ACCEPTED",
        "timestamp_utc": now_utc_iso(),
        "exchange": "MOCK",
        "symbol": order_request.get("symbol"),
        "side": order_request.get("side"),
        "order_type": order_request.get("order_type"),
        "filled_price": filled_price,
        "filled_quantity": filled_quantity,
        "notional_usdt": round(filled_price * filled_quantity, 8),
        "order_request": order_request,
        "raw_response": {
            "mock": True,
            "live_order_executed": False,
        },
    }
    save_json(storage_path / "mock_order_result.json", result)
    append_json_log(storage_path / "mock_order_log.json", result)
    return result
