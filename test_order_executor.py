from __future__ import annotations

from execution.order_executor import execute_order_with_risk_check


def main() -> None:
    result = execute_order_with_risk_check("BTCUSDT", "BUY", 0.00005, price=107500, current_price=107500, storage_dir="storage", metadata={"source": "test_order_executor"})
    print("[ORDER EXECUTOR TEST]")
    print(f"Status: {result.get('status')}")
    print(f"Executed: {result.get('executed')}")
    risk = result.get("risk_result") or {}
    print(f"Risk Status: {risk.get('status')}")
    print(f"Approved: {risk.get('approved')}")


if __name__ == "__main__":
    main()
