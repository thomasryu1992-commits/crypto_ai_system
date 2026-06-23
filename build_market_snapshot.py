from core.console import configure_utf8_console, safe_print
from builders.market_snapshot_builder import build_market_snapshot

configure_utf8_console()


def main() -> dict:
    result = build_market_snapshot()
    safe_print("[MARKET SNAPSHOT BUILDER]")
    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Current Price: {result.get('current_price')}")
    return result


if __name__ == "__main__":
    main()
