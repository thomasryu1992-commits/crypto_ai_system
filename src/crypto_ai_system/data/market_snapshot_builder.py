from __future__ import annotations

import pandas as pd

from crypto_ai_system.data.schemas import MarketSnapshot


def _last_close(df: pd.DataFrame) -> float | None:
    if df is None or df.empty or 'close' not in df.columns:
        return None
    try:
        return float(df.iloc[-1]['close'])
    except Exception:
        return None


def build_market_snapshot(
    ohlcv: pd.DataFrame,
    derivatives: pd.DataFrame,
    source: str = 'mixed',
    mark: pd.DataFrame | None = None,
    index: pd.DataFrame | None = None,
    orderbook: dict | None = None,
) -> MarketSnapshot:
    if ohlcv.empty:
        raise ValueError('OHLCV data is empty')
    last = ohlcv.iloc[-1]
    der = derivatives.iloc[-1] if derivatives is not None and not derivatives.empty else {}
    orderbook = orderbook or {}
    spread_bps = orderbook.get('spread_bps')
    return MarketSnapshot(
        symbol=str(last.get('symbol', 'BTC-PERP')),
        timeframe=str(last.get('timeframe', 'PT1H')),
        timestamp=str(last['timestamp']),
        source=source,
        open=float(last['open']),
        high=float(last['high']),
        low=float(last['low']),
        close=float(last['close']),
        volume=float(last['volume']),
        exchange=str(last.get('exchange', 'extended')),
        exchange_market=str(last.get('exchange_market', 'BTC-USD')),
        base_asset='BTC' if str(last.get('symbol', 'BTC-PERP')).startswith('BTC') else str(last.get('base_asset', 'UNKNOWN')),
        quote_asset='USD',
        settlement_asset='USDC',
        contract_type='PERPETUAL',
        mark_price=_last_close(mark),
        index_price=_last_close(index),
        funding_rate=float(der.get('funding_rate')) if 'funding_rate' in der else None,
        open_interest=float(der.get('open_interest')) if 'open_interest' in der else None,
        open_interest_base=float(der.get('open_interest_base')) if 'open_interest_base' in der else None,
        oi_change_pct=float(der.get('oi_change_pct')) if 'oi_change_pct' in der else None,
        long_liquidation=float(der.get('long_liquidation')) if 'long_liquidation' in der else None,
        short_liquidation=float(der.get('short_liquidation')) if 'short_liquidation' in der else None,
        bid_price=float(orderbook['bid_price']) if orderbook.get('bid_price') is not None else None,
        ask_price=float(orderbook['ask_price']) if orderbook.get('ask_price') is not None else None,
        spread_bps=float(spread_bps) if spread_bps is not None else None,
        data_quality_status='OK' if not str(source).startswith('sample') else 'SAMPLE_FALLBACK'
    )
