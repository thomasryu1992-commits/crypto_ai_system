from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtendedBacktestCostModel:
    maker_fee_bps: float = 0.0
    taker_fee_bps: float = 2.5
    slippage_bps: float = 3.0
    settlement_asset: str = 'USDC'


@dataclass(frozen=True)
class ExtendedExecutionNotes:
    price_parameter_required: bool = True
    market_order_mode: str = 'limit_ioc_crossing_price'
    signed_order_required: bool = True
    websocket_order_tracking_required: bool = True
