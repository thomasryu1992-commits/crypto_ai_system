from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd
import requests

from crypto_ai_system.config import AppConfig


@dataclass(frozen=True)
class DefiLlamaCollectorResult:
    frames: Dict[str, pd.DataFrame]
    status: Dict[str, Any]


class DefiLlamaStablecoinClient:
    """DefiLlama free stablecoin API collector."""

    def __init__(self, base_url: str = 'https://stablecoins.llama.fi', timeout_seconds: float = 8.0) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'crypto-ai-system-defillama-stablecoins/1.0'})

    @classmethod
    def from_config(cls, cfg: AppConfig) -> 'DefiLlamaStablecoinClient':
        base = str(cfg.get('additional_data.defillama.base_url', 'https://stablecoins.llama.fi'))
        timeout = float(cfg.get('additional_data.defillama.timeout_seconds', cfg.get('additional_data.timeout_seconds', 8)))
        return cls(base_url=base, timeout_seconds=timeout)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(f'{self.base_url}{path}', params=params or {}, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def current_stablecoins(self) -> pd.DataFrame:
        payload = self._get('/stablecoins', {'includePrices': 'true'})
        pegged = payload.get('peggedAssets') or []
        rows = []
        now = pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S+00:00')
        for item in pegged:
            symbol = str(item.get('symbol') or item.get('name') or '').upper()
            circulating = item.get('circulating') or {}
            pegged_usd = None
            if isinstance(circulating, dict):
                pegged_usd = circulating.get('peggedUSD') or circulating.get('usd')
            rows.append({
                'timestamp': now,
                'stablecoin_symbol': symbol,
                'stablecoin_name': item.get('name'),
                'mcap_usd': _number(pegged_usd or item.get('mcap') or item.get('marketCap')),
                'peg_type': item.get('pegType'),
                'price_source': item.get('priceSource'),
                'source': 'defillama_stablecoins',
            })
        return pd.DataFrame(rows)

    def stablecoin_charts_all(self) -> pd.DataFrame:
        payload = self._get('/stablecoincharts/all')
        rows = []
        series = payload if isinstance(payload, list) else payload.get('data', []) if isinstance(payload, dict) else []
        for item in series or []:
            date_value = item.get('date') or item.get('timestamp') or item.get('time')
            total = item.get('totalCirculating') or item.get('totalCirculatingUSD') or item.get('total') or {}
            pegged_usd = total.get('peggedUSD') if isinstance(total, dict) else total
            rows.append({
                'timestamp': _to_timestamp(date_value),
                'stablecoin_total_mcap': _number(pegged_usd),
                'source': 'defillama_stablecoins',
            })
        return pd.DataFrame(rows)


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default


def _to_timestamp(value: Any) -> str:
    try:
        if value is None:
            return pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S+00:00')
        v = float(value)
        unit = 'ms' if v > 10_000_000_000 else 's'
        return pd.to_datetime(v, unit=unit, utc=True).strftime('%Y-%m-%d %H:%M:%S+00:00')
    except Exception:
        ts = pd.to_datetime(value, utc=True, errors='coerce')
        if pd.isna(ts):
            return pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S+00:00')
        return ts.strftime('%Y-%m-%d %H:%M:%S+00:00')


def collect_defillama_stablecoins(cfg: AppConfig) -> DefiLlamaCollectorResult:
    enabled = bool(cfg.get('additional_data.defillama.enabled', True))
    if not enabled:
        return DefiLlamaCollectorResult(frames={}, status={'enabled': False, 'ok': True, 'source': 'defillama_stablecoins'})

    client = DefiLlamaStablecoinClient.from_config(cfg)
    frames: Dict[str, pd.DataFrame] = {}
    errors: Dict[str, str] = {}
    for name, fn in [
        ('defillama_stablecoins_current', client.current_stablecoins),
        ('defillama_stablecoin_charts_all', client.stablecoin_charts_all),
    ]:
        try:
            frame = fn()
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                frames[name] = frame.sort_values('timestamp').reset_index(drop=True) if 'timestamp' in frame.columns else frame
        except Exception as exc:
            errors[name] = str(exc)
    return DefiLlamaCollectorResult(frames=frames, status={
        'enabled': True,
        'ok': bool(frames),
        'source': 'defillama_stablecoins',
        'frames': {k: len(v) for k, v in frames.items()},
        'errors': errors,
    })
