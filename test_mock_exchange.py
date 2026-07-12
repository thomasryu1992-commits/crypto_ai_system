from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.execution.order_executor import place_order


def test_mock_exchange_is_blocked() -> None:
    assert place_order({"mock": True})["status"] == "BLOCKED_STEP80"


if __name__ == "__main__":
    test_mock_exchange_is_blocked()
    print("PASSED")
