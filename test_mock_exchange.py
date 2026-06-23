from __future__ import annotations

from execution.order_models import create_order_request
from execution.exchange_router import route_order


def main() -> None:
    order = create_order_request("BTCUSDT", "BUY", 0.00005, price=107500, metadata={"source": "test_mock_exchange"})
    result = route_order(order, current_price=107500, storage_dir="storage")
    print("[MOCK EXCHANGE TEST]")
    print(f"Status: {result.get('status')}")
    order_result = result.get("order_result") or {}
    print(f"Order Status: {order_result.get('status')}")
    print(f"Live Executed: {(order_result.get('raw_response') or {}).get('live_order_executed')}")


if __name__ == "__main__":
    main()
