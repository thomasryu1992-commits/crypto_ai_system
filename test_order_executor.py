from __future__ import annotations

from execution.order_executor import place_order


def test_live_order_blocked() -> None:
    result = place_order({"symbol": "BTCUSDT", "side": "BUY"})
    assert result["status"] == "BLOCKED_STEP80"


if __name__ == "__main__":
    test_live_order_blocked()
    print("PASSED")
