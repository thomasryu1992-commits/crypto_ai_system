from __future__ import annotations

from collectors.market_data_collector import collect_market_data


def test_collect_market_data_fallback() -> None:
    result = collect_market_data()
    assert result["candles"]
    assert result["derivatives"]


if __name__ == "__main__":
    test_collect_market_data_fallback()
    print("PASSED")
