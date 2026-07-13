from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class MarketIdentity:
    canonical_symbol: str
    exchange: str
    exchange_market: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    contract_type: str
    timeframe: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    timestamp: str
    source: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    exchange: str = 'extended'
    exchange_market: str = 'BTC-USD'
    base_asset: str = 'BTC'
    quote_asset: str = 'USD'
    settlement_asset: str = 'USDC'
    contract_type: str = 'PERPETUAL'
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    open_interest_base: float | None = None
    oi_change_pct: float | None = None
    long_liquidation: float | None = None
    short_liquidation: float | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    spread_bps: float | None = None
    data_quality_status: str = 'OK'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
