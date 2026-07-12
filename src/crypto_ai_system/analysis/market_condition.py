from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

import pandas as pd


@dataclass
class MarketCondition:
    timestamp: str
    symbol: str
    regime: str
    score_bias: str
    total_score: float
    volatility_state: str
    derivatives_state: str
    liquidity_state: str
    final_condition: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_market_condition(row: pd.Series | Dict[str, Any]) -> MarketCondition:
    r = row if isinstance(row, dict) else row.to_dict()
    atr_pct = float(r.get('atr_pct_of_price') or 0)
    spread_bps = float(r.get('spread_bps') or 0)
    funding_z = float(r.get('funding_zscore') or 0)
    oi_change = float(r.get('oi_change_pct') or 0)
    binance_derivatives_score = float(r.get('binance_derivatives_score') or 0)
    exchange_flow_score = float(r.get('exchange_flow_score') or 0)
    etf_flow_score = float(r.get('etf_flow_score') or 0)
    stablecoin_liquidity_score = float(r.get('stablecoin_liquidity_score') or 0)
    score = float(r.get('score_total_score') or r.get('total_score') or 0)
    bias = str(r.get('score_bias') or r.get('bias') or 'NEUTRAL')
    regime = str(r.get('market_regime') or 'UNCLEAR')

    volatility_state = 'HIGH_VOLATILITY' if atr_pct >= 0.025 else 'LOW_VOLATILITY' if atr_pct <= 0.006 else 'NORMAL_VOLATILITY'
    liquidity_state = 'POOR_LIQUIDITY' if spread_bps >= 10 else 'NORMAL_LIQUIDITY'
    if abs(funding_z) >= 2.5 or abs(binance_derivatives_score) >= 0.85:
        derivatives_state = 'CROWDED_POSITIONING'
    elif abs(oi_change) >= 0.025:
        derivatives_state = 'OI_EXPANSION'
    else:
        derivatives_state = 'NORMAL_DERIVATIVES'

    if stablecoin_liquidity_score <= -0.75 or etf_flow_score <= -0.85:
        liquidity_state = 'RISK_OFF_LIQUIDITY'

    if liquidity_state == 'POOR_LIQUIDITY':
        final = 'NO_TRADE_LIQUIDITY'
    elif derivatives_state == 'CROWDED_POSITIONING' and abs(score) < 0.75:
        final = 'OVERLEVERAGED_WAIT'
    elif exchange_flow_score <= -0.85 and abs(score) < 0.70:
        final = 'WAIT_EXCHANGE_SELL_PRESSURE'
    elif liquidity_state == 'RISK_OFF_LIQUIDITY' and abs(score) < 0.75:
        final = 'RISK_OFF_WAIT'
    elif volatility_state == 'HIGH_VOLATILITY' and abs(score) < 0.55:
        final = 'WAIT_HIGH_VOLATILITY'
    elif regime.startswith('TREND') and abs(score) >= 0.35:
        final = f'{bias}_TREND_OPPORTUNITY'
    elif regime == 'RANGE' and abs(score) >= 0.45:
        final = f'{bias}_RANGE_REVERSAL_CANDIDATE'
    else:
        final = 'NEUTRAL_WAIT'

    return MarketCondition(
        timestamp=str(r.get('timestamp') or ''),
        symbol=str(r.get('canonical_symbol') or r.get('symbol') or 'BTC-PERP'),
        regime=regime,
        score_bias=bias,
        total_score=score,
        volatility_state=volatility_state,
        derivatives_state=derivatives_state,
        liquidity_state=liquidity_state,
        final_condition=final,
    )
