from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import pandas as pd
import requests


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _history_value(row: Dict[str, Any], preferred: Iterable[str]) -> float | None:
    for key in preferred:
        if key in row:
            value = _to_float(row.get(key))
            if value is not None:
                return value
    # Coinalyze history rows often use o/h/l/c. Use close first, then value-like fields.
    for key in ('c', 'value', 'v', 'o', 'h', 'l'):
        if key in row:
            value = _to_float(row.get(key))
            if value is not None:
                return value
    return None


def _normalize_ts_seconds(value: Any) -> str | None:
    numeric = pd.to_numeric(value, errors='coerce')
    if pd.isna(numeric):
        return None
    unit = 'ms' if float(numeric) > 10_000_000_000 else 's'
    return pd.to_datetime(float(numeric), unit=unit, utc=True).strftime('%Y-%m-%d %H:%M:%S+00:00')


@dataclass
class CoinalyzeClient:
    """Coinalyze derivatives client.

    Supported endpoints are kept small and explicit: futures market discovery,
    open-interest history, funding-rate history, liquidation history, and
    long/short ratio history. Missing API keys or plan-restricted endpoints fail
    transparently so the pipeline can mark Coinalyze as skipped instead of
    pretending synthetic derivatives are real.
    """

    api_key: str | None = None
    base_url: str | None = None
    timeout: int = 10

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv('COINALYZE_API_KEY')
        self.base_url = (self.base_url or os.getenv('COINALYZE_BASE_URL') or 'https://api.coinalyze.net/v1').rstrip('/')

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError('COINALYZE_API_KEY is not configured')
        return {'api_key': self.api_key}

    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.get(url, params=params or {}, headers=self._headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_future_markets(self) -> list[dict[str, Any]]:
        payload = self._get('future-markets')
        if isinstance(payload, list):
            return [dict(x) for x in payload]
        return list(payload.get('data', [])) if isinstance(payload, dict) else []

    def _history_endpoint(self, endpoint: str, symbol: str, interval: str, limit: int, from_ts: int | None = None, to_ts: int | None = None) -> list[dict[str, Any]]:
        to_ts = int(to_ts or time.time())
        from_ts = int(from_ts or (to_ts - max(int(limit), 24) * 3600))
        params = {'symbols': symbol, 'interval': interval, 'from': from_ts, 'to': to_ts}
        payload = self._get(endpoint, params=params)
        if isinstance(payload, dict) and 'data' in payload:
            payload = payload['data']
        if not isinstance(payload, list):
            return []
        return [dict(x) for x in payload]

    def get_open_interest_history(self, symbol: str, interval: str = '1hour', limit: int = 500) -> pd.DataFrame:
        rows = self._history_endpoint('open-interest-history', symbol, interval, limit)
        records: list[dict[str, Any]] = []
        for item in rows:
            item_symbol = item.get('symbol') or symbol
            for h in item.get('history') or []:
                ts = _normalize_ts_seconds(h.get('t'))
                value = _history_value(h, ('c', 'value', 'oi', 'open_interest'))
                if ts is not None and value is not None:
                    records.append({'timestamp': ts, 'coinalyze_symbol': item_symbol, 'open_interest': value, 'source': 'coinalyze'})
        return pd.DataFrame(records)

    def get_funding_rate_history(self, symbol: str, interval: str = '1hour', limit: int = 500) -> pd.DataFrame:
        rows = self._history_endpoint('funding-rate-history', symbol, interval, limit)
        records: list[dict[str, Any]] = []
        for item in rows:
            item_symbol = item.get('symbol') or symbol
            for h in item.get('history') or []:
                ts = _normalize_ts_seconds(h.get('t'))
                value = _history_value(h, ('c', 'value', 'funding_rate'))
                if ts is not None and value is not None:
                    records.append({'timestamp': ts, 'coinalyze_symbol': item_symbol, 'funding_rate': value, 'source': 'coinalyze'})
        return pd.DataFrame(records)

    def get_liquidation_history(self, symbol: str, interval: str = '1hour', limit: int = 500) -> pd.DataFrame:
        rows = self._history_endpoint('liquidation-history', symbol, interval, limit)
        records: list[dict[str, Any]] = []
        for item in rows:
            item_symbol = item.get('symbol') or symbol
            for h in item.get('history') or []:
                ts = _normalize_ts_seconds(h.get('t'))
                long_liq = _to_float(h.get('l'), 0.0) or 0.0
                short_liq = _to_float(h.get('s'), 0.0) or 0.0
                if ts is not None:
                    records.append({'timestamp': ts, 'coinalyze_symbol': item_symbol, 'long_liquidation': long_liq, 'short_liquidation': short_liq, 'source': 'coinalyze'})
        return pd.DataFrame(records)

    def get_long_short_ratio_history(self, symbol: str, interval: str = '1hour', limit: int = 500) -> pd.DataFrame:
        rows = self._history_endpoint('long-short-ratio-history', symbol, interval, limit)
        records: list[dict[str, Any]] = []
        for item in rows:
            item_symbol = item.get('symbol') or symbol
            for h in item.get('history') or []:
                ts = _normalize_ts_seconds(h.get('t'))
                value = _history_value(h, ('r', 'c', 'value', 'long_short_ratio'))
                if ts is not None and value is not None:
                    records.append({'timestamp': ts, 'coinalyze_symbol': item_symbol, 'long_short_ratio': value, 'source': 'coinalyze'})
        return pd.DataFrame(records)

    def get_derivatives_if_configured(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        funding = self.get_funding_rate_history(symbol=symbol, interval=interval, limit=limit)
        oi = self.get_open_interest_history(symbol=symbol, interval=interval, limit=limit)
        liq = self.get_liquidation_history(symbol=symbol, interval=interval, limit=limit)
        try:
            long_short = self.get_long_short_ratio_history(symbol=symbol, interval=interval, limit=limit)
        except Exception:
            long_short = pd.DataFrame()

        frames = [x for x in [funding, oi, liq, long_short] if isinstance(x, pd.DataFrame) and not x.empty]
        if not frames:
            return pd.DataFrame()
        out = frames[0]
        for frame in frames[1:]:
            out = out.merge(frame, on=['timestamp', 'coinalyze_symbol', 'source'], how='outer')
        out = out.sort_values('timestamp').tail(limit).reset_index(drop=True)
        out['funding_rate'] = pd.to_numeric(out.get('funding_rate', 0), errors='coerce').fillna(0)
        out['open_interest'] = pd.to_numeric(out.get('open_interest', 0), errors='coerce').ffill().fillna(0)
        out['open_interest_base'] = 0.0
        out['oi_change_pct'] = out['open_interest'].pct_change().replace([float('inf'), float('-inf')], 0).fillna(0)
        out['long_liquidation'] = pd.to_numeric(out.get('long_liquidation', 0), errors='coerce').fillna(0)
        out['short_liquidation'] = pd.to_numeric(out.get('short_liquidation', 0), errors='coerce').fillna(0)
        return out
