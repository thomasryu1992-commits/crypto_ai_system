from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from scripts.json_utils import now_utc_iso, to_float


def create_order_request(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "MARKET",
    price: Optional[float] = None,
    reduce_only: bool = False,
    mode: str = "PAPER_ONLY",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    request = {
        "request_id": f"order_req_{uuid.uuid4().hex[:12]}",
        "timestamp_utc": now_utc_iso(),
        "symbol": str(symbol).upper(),
        "side": str(side).upper(),
        "order_type": str(order_type).upper(),
        "quantity": quantity,
        "price": price,
        "reduce_only": bool(reduce_only),
        "mode": mode,
        "metadata": metadata or {},
    }
    request["validation"] = validate_order_request(request)
    return request


def validate_order_request(order_request: Dict[str, Any]) -> Dict[str, Any]:
    errors = []
    if not order_request.get("symbol"):
        errors.append("symbol is required")
    if order_request.get("side") not in {"BUY", "SELL"}:
        errors.append("side must be BUY or SELL")
    if order_request.get("order_type") not in {"MARKET", "LIMIT"}:
        errors.append("order_type must be MARKET or LIMIT")
    quantity = to_float(order_request.get("quantity"))
    if quantity is None or quantity <= 0:
        errors.append("quantity must be positive")
    if order_request.get("order_type") == "LIMIT":
        price = to_float(order_request.get("price"))
        if price is None or price <= 0:
            errors.append("limit order price must be positive")
    return {"valid": not errors, "errors": errors}
