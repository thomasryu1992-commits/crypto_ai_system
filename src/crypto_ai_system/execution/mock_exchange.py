from __future__ import annotations

from core.time_utils import utc_now_iso


MOCK_EXCHANGE_MODE = "LOCAL_TEST_SUPPORT_ONLY"
NETWORK_CALLS_PERFORMED = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False


class MockExchangeClient:
    def place_order(self, symbol: str, side: str, quantity: float, price: float | None = None, reduce_only: bool = False) -> dict:
        return {
            "status": "MOCK_FILLED",
            "generated_at": utc_now_iso(),
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "reduce_only": reduce_only,
            "exchange_order_id": "mock-order-step120",
        }



def place_mock_order(order_request: dict, current_price=None, storage_dir=None) -> dict:
    """Deterministic local mock order helper for review-only router tests.

    No network calls and no external exchange submission are performed.
    """
    client = MockExchangeClient()
    price = current_price if current_price is not None else order_request.get("price")
    return {
        **client.place_order(
            symbol=order_request.get("symbol", "UNKNOWN"),
            side=order_request.get("side", "BUY"),
            quantity=order_request.get("quantity", 0),
            price=price,
            reduce_only=bool(order_request.get("reduce_only", False)),
        ),
        "mock_exchange_mode": MOCK_EXCHANGE_MODE,
        "network_calls_performed": NETWORK_CALLS_PERFORMED,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "storage_dir": str(storage_dir) if storage_dir is not None else None,
    }
