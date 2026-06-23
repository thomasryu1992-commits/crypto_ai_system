from __future__ import annotations

from builders.market_context import build_market_context
from core.console import configure_utf8_console, safe_print


def main() -> None:
    configure_utf8_console()
    result = build_market_context()
    safe_print("Market context:", result.get("summary"))


if __name__ == "__main__":
    main()
