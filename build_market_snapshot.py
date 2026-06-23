from __future__ import annotations

from builders.market_snapshot import build_market_snapshot
from core.console import configure_utf8_console, safe_print


def main() -> None:
    configure_utf8_console()
    result = build_market_snapshot()
    safe_print("Market snapshot:", result)


if __name__ == "__main__":
    main()
