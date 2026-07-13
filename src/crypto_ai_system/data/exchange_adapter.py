from __future__ import annotations

from typing import Protocol

import pandas as pd

from crypto_ai_system.data.schemas import MarketIdentity


class ExchangeMarketDataAdapter(Protocol):
    def get_ohlcv(self, market: MarketIdentity, limit: int) -> pd.DataFrame:
        ...

    def get_derivatives(self, market: MarketIdentity, limit: int) -> pd.DataFrame:
        ...

    def get_orderbook_snapshot(self, market: MarketIdentity) -> dict:
        ...
