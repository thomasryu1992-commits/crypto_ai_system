from __future__ import annotations

from core.time_utils import utc_now_iso


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
