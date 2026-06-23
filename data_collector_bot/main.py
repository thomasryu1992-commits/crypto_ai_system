from __future__ import annotations

from config.settings import STORAGE_DIR, ensure_base_dirs
from data_collector_bot.market_context_builder import build_market_context
from scripts.json_utils import save_json


def run_data_collector() -> dict:
    ensure_base_dirs()
    market_context = build_market_context()
    path = STORAGE_DIR / "market_context.json"
    save_json(path, market_context)

    if market_context.get("status") == "ERROR":
        status = "MARKET_CONTEXT_ERROR"
    elif market_context.get("data_mode") == "synthetic_test_only":
        status = "SYNTHETIC_MARKET_CONTEXT_CREATED"
    elif market_context.get("data_mode") == "real_or_prepared":
        status = "MARKET_CONTEXT_REUSED"
    else:
        status = "MARKET_CONTEXT_CREATED"

    return {
        "status": status,
        "path": str(path),
        "symbol": market_context.get("symbol"),
        "current_price": market_context.get("current_price"),
        "data_mode": market_context.get("data_mode"),
        "error_message": market_context.get("error_message"),
    }


def main() -> None:
    result = run_data_collector()
    print("[DATA COLLECTOR]")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
