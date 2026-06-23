from core.console import configure_utf8_console, safe_print
from builders.market_context_builder import build_market_context

configure_utf8_console()


def main() -> dict:
    result = build_market_context()
    safe_print("[MARKET CONTEXT BUILDER]")
    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Market Bias: {result.get('market_bias')}")
    return result


if __name__ == "__main__":
    main()
