from __future__ import annotations

from collectors.market_data_collector import collect_market_data
from core.console import configure_utf8_console, safe_print


def main() -> None:
    configure_utf8_console()
    result = collect_market_data()
    safe_print("Market data collected:", result.get("source"), result.get("generated_at"))


if __name__ == "__main__":
    main()
