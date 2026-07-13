from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class ScenarioSet:
    base_case: str
    bullish_case: str
    bearish_case: str
    invalidation: str
    key_watchlist: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_scenarios(snapshot: Dict[str, Any]) -> ScenarioSet:
    score = float(snapshot.get('score_total_score') or snapshot.get('total_score') or 0)
    regime = str(snapshot.get('market_regime') or 'UNCLEAR')
    close = float(snapshot.get('close') or 0)
    ma20 = float(snapshot.get('ma20') or close)
    ma50 = float(snapshot.get('ma50') or close)
    atr = float(snapshot.get('atr') or 0)
    funding = float(snapshot.get('funding_rate') or 0)
    oi_change = float(snapshot.get('oi_change_pct') or 0)
    exchange_flow_score = float(snapshot.get('exchange_flow_score') or 0)
    etf_flow_score = float(snapshot.get('etf_flow_score') or 0)
    stablecoin_liquidity_score = float(snapshot.get('stablecoin_liquidity_score') or 0)

    if score >= 0.35:
        base = 'Bullish-to-neutral: score and structure favor long-side setups, but execution still requires liquidity and risk guards.'
    elif score <= -0.35:
        base = 'Bearish-to-neutral: score and structure favor short-side setups, but execution still requires confirmation and risk guards.'
    else:
        base = 'Neutral: no clear asymmetric setup. Preserve capital and wait for cleaner regime confirmation.'

    bullish = (
        f'Bullish case: price holds above MA20 ({ma20:.2f}) and MA50 ({ma50:.2f}), OI expansion remains controlled '
        f'({oi_change:.2%}), funding does not become excessively crowded ({funding:.5f}), and flow/liquidity confirmation improves '
        f'(exchange {exchange_flow_score:.2f}, ETF {etf_flow_score:.2f}, stablecoin {stablecoin_liquidity_score:.2f}).'
    )
    bearish = (
        f'Bearish case: price loses MA20/MA50 support, mark/index basis weakens, exchange netflow turns into sell pressure, '
        f'ETF flow deteriorates, and liquidation or OI expansion confirms downside continuation.'
    )
    inv = f'Invalidation: close crosses against the active setup by more than ATR buffer ({atr:.2f}) or regime flips from {regime} to UNCLEAR/RANGE.'
    watch = ['MA20/MA50 alignment', 'ADX/regime label', 'funding z-score', 'OI change', 'Binance taker buy/sell ratio', 'exchange netflow z-score', 'ETF 5d flow', 'stablecoin 7d supply change', 'spread bps', 'liquidation imbalance']
    if close:
        watch.insert(0, f'Current close: {close:.2f}')
    return ScenarioSet(base, bullish, bearish, inv, watch)
