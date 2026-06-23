from __future__ import annotations

from collectors.market_data_collector import collect_market_data


def run() -> dict:
    return collect_market_data()
