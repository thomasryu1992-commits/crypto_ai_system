from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd
import requests

from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.schemas import MarketIdentity


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_base_url(raw: str) -> str:
    base = raw.rstrip('/')
    if not base.endswith('/api/v1'):
        base = base + '/api/v1'
    return base


@dataclass
class ExtendedClient:
    base_url: str
    api_key: str | None = None
    timeout: int = 10
    user_agent: str = 'crypto_ai_system_step157e/0.1'

    @classmethod
    def from_config(cls, cfg: AppConfig) -> 'ExtendedClient':
        env = str(cfg.get('extended.environment', 'mainnet')).lower()
        configured = cfg.get('extended.base_url')
        if configured:
            base_url = configured
        elif env == 'testnet':
            base_url = str(cfg.get('extended.testnet_base_url', 'https://api.starknet.sepolia.extended.exchange/api/v1'))
        else:
            base_url = str(cfg.get('extended.mainnet_base_url', 'https://api.starknet.extended.exchange/api/v1'))
        return cls(
            base_url=_normalize_base_url(base_url),
            api_key=cfg.get('extended.api_key') or os.getenv('EXTENDED_API_KEY'),
            timeout=int(cfg.get('extended.timeout_seconds', 10)),
            user_agent=str(cfg.get('extended.user_agent', 'crypto_ai_system_step157e/0.1')),
        )

    def _headers(self) -> Dict[str, str]:
        headers = {'User-Agent': self.user_agent}
        if self.api_key:
            headers['X-Api-Key'] = self.api_key
        return headers

    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.get(url, params=params or {}, headers=self._headers(), timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get('status', '')).upper()
        if status and status not in {'OK', 'SUCCESS'}:
            raise RuntimeError(f"Extended API error: {payload.get('error') or payload}")
        return payload.get('data', payload)

    def get_market_stats(self, market: MarketIdentity) -> Dict[str, Any]:
        return dict(self._get(f'info/markets/{market.exchange_market}/stats'))

    def get_orderbook_snapshot(self, market: MarketIdentity) -> Dict[str, Any]:
        data = self._get(f'info/markets/{market.exchange_market}/orderbook')
        bids = data.get('bid') or data.get('bids') or []
        asks = data.get('ask') or data.get('asks') or []
        bid = _as_float(bids[0].get('price')) if bids else None
        ask = _as_float(asks[0].get('price')) if asks else None
        spread_bps = None
        if bid and ask and bid > 0:
            spread_bps = (ask - bid) / ((ask + bid) / 2) * 10000
        return {
            'exchange_market': data.get('market', market.exchange_market),
            'bid_price': bid,
            'ask_price': ask,
            'spread_bps': spread_bps,
            'raw_bid_levels': bids[:5],
            'raw_ask_levels': asks[:5],
        }

    def get_candles(self, market: MarketIdentity, candle_type: str = 'trades', limit: int = 500, end_time_ms: int | None = None) -> pd.DataFrame:
        params = {'interval': market.timeframe, 'limit': int(limit)}
        if end_time_ms is not None:
            params['endTime'] = int(end_time_ms)
        rows = list(self._get(f'info/candles/{market.exchange_market}/{candle_type}', params=params))
        if not rows:
            raise ValueError('Extended returned no candle rows')
        df = pd.DataFrame(rows)
        t_col = 'T' if 'T' in df.columns else 't'
        df['timestamp'] = pd.to_datetime(pd.to_numeric(df[t_col], errors='coerce'), unit='ms', utc=True).astype(str)
        out = pd.DataFrame({
            'timestamp': df['timestamp'],
            'symbol': market.canonical_symbol,
            'exchange': market.exchange,
            'exchange_market': market.exchange_market,
            'timeframe': market.timeframe,
            'open': pd.to_numeric(df.get('o'), errors='coerce'),
            'high': pd.to_numeric(df.get('h'), errors='coerce'),
            'low': pd.to_numeric(df.get('l'), errors='coerce'),
            'close': pd.to_numeric(df.get('c'), errors='coerce'),
            'volume': pd.to_numeric(df.get('v', 0), errors='coerce').fillna(0),
            'source': f'extended_{candle_type}',
        })
        return out.sort_values('timestamp').dropna(subset=['open', 'high', 'low', 'close']).reset_index(drop=True)

    def get_funding_history(self, market: MarketIdentity, hours: int = 500, limit: int = 500) -> pd.DataFrame:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - int(hours * 3600 * 1000)
        params = {'startTime': start_ms, 'endTime': end_ms, 'limit': int(limit)}
        rows = list(self._get(f'info/{market.exchange_market}/funding', params=params))
        if not rows:
            return pd.DataFrame(columns=['timestamp', 'funding_rate'])
        df = pd.DataFrame(rows)
        df['timestamp'] = pd.to_datetime(pd.to_numeric(df['T'], errors='coerce'), unit='ms', utc=True).dt.floor('h').astype(str)
        df['funding_rate'] = pd.to_numeric(df['f'], errors='coerce')
        return df[['timestamp', 'funding_rate']].sort_values('timestamp').dropna().reset_index(drop=True)

    def get_open_interest_history(self, market: MarketIdentity, hours: int = 300, limit: int = 300) -> pd.DataFrame:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - int(hours * 3600 * 1000)
        interval = 'P1H' if market.timeframe in {'PT1H', '1h', '1H'} else 'P1D'
        params = {'interval': interval, 'startTime': start_ms, 'endTime': end_ms, 'limit': int(limit)}
        rows = list(self._get(f'info/{market.exchange_market}/open-interests', params=params))
        if not rows:
            return pd.DataFrame(columns=['timestamp', 'open_interest', 'open_interest_base'])
        df = pd.DataFrame(rows)
        df['timestamp'] = pd.to_datetime(pd.to_numeric(df['t'], errors='coerce'), unit='ms', utc=True).dt.floor('h').astype(str)
        df['open_interest'] = pd.to_numeric(df['i'], errors='coerce')
        df['open_interest_base'] = pd.to_numeric(df['I'], errors='coerce')
        return df[['timestamp', 'open_interest', 'open_interest_base']].sort_values('timestamp').dropna(subset=['open_interest']).reset_index(drop=True)

    def get_recent_trades(self, market: MarketIdentity) -> pd.DataFrame:
        rows = list(self._get(f'info/markets/{market.exchange_market}/trades'))
        if not rows:
            return pd.DataFrame(columns=['timestamp', 'side', 'trade_type', 'price', 'qty', 'notional'])
        df = pd.DataFrame(rows)
        df['timestamp'] = pd.to_datetime(pd.to_numeric(df['T'], errors='coerce'), unit='ms', utc=True).dt.floor('h').astype(str)
        df['side'] = df['S'].astype(str).str.upper()
        df['trade_type'] = df['tT'].astype(str).str.upper()
        df['price'] = pd.to_numeric(df['p'], errors='coerce')
        df['qty'] = pd.to_numeric(df['q'], errors='coerce')
        df['notional'] = df['price'] * df['qty']
        return df[['timestamp', 'side', 'trade_type', 'price', 'qty', 'notional']].dropna(subset=['price', 'qty']).reset_index(drop=True)

    def get_derivatives(self, market: MarketIdentity, limit: int, funding_hours: int = 500, oi_hours: int = 300) -> pd.DataFrame:
        funding = self.get_funding_history(market, hours=funding_hours, limit=max(limit, 50))
        oi = self.get_open_interest_history(market, hours=min(max(oi_hours, 24), 300), limit=min(max(limit, 50), 300))
        if funding.empty and oi.empty:
            raise ValueError('Extended returned no derivatives rows')
        if funding.empty:
            der = oi.copy()
            der['funding_rate'] = 0.0
        elif oi.empty:
            der = funding.copy()
            der['open_interest'] = 0.0
            der['open_interest_base'] = 0.0
        else:
            der = funding.merge(oi, on='timestamp', how='outer').sort_values('timestamp').reset_index(drop=True)
        der['symbol'] = market.canonical_symbol
        der['exchange'] = market.exchange
        der['exchange_market'] = market.exchange_market
        der['timeframe'] = market.timeframe
        der['open_interest'] = pd.to_numeric(der.get('open_interest', 0), errors='coerce').ffill().fillna(0)
        der['open_interest_base'] = pd.to_numeric(der.get('open_interest_base', 0), errors='coerce').ffill().fillna(0)
        der['funding_rate'] = pd.to_numeric(der.get('funding_rate', 0), errors='coerce').fillna(0)
        der['oi_change_pct'] = der['open_interest'].pct_change().replace([float('inf'), float('-inf')], 0).fillna(0)
        der['long_liquidation'] = 0.0
        der['short_liquidation'] = 0.0
        try:
            trades = self.get_recent_trades(market)
            liq = trades[trades['trade_type'].isin(['LIQUIDATION', 'DELEVERAGE'])].copy()
            if not liq.empty:
                grouped = liq.groupby(['timestamp', 'side'])['notional'].sum().unstack(fill_value=0).reset_index()
                grouped['long_liquidation'] = grouped.get('SELL', 0.0)
                grouped['short_liquidation'] = grouped.get('BUY', 0.0)
                der = der.merge(grouped[['timestamp', 'long_liquidation', 'short_liquidation']], on='timestamp', how='left', suffixes=('', '_event'))
                der['long_liquidation'] = der.get('long_liquidation_event', der['long_liquidation']).fillna(der['long_liquidation'])
                der['short_liquidation'] = der.get('short_liquidation_event', der['short_liquidation']).fillna(der['short_liquidation'])
        except Exception:
            pass
        der['source'] = 'extended'
        cols = ['timestamp', 'symbol', 'exchange', 'exchange_market', 'timeframe', 'funding_rate', 'open_interest', 'open_interest_base', 'oi_change_pct', 'long_liquidation', 'short_liquidation', 'source']
        return der[[c for c in cols if c in der.columns]].sort_values('timestamp').tail(limit).reset_index(drop=True)
