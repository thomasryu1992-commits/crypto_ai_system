from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

import pandas as pd
import requests
from requests import RequestException

from crypto_ai_system.config import AppConfig


DEFAULT_EXCHANGE_FLOW_METRICS = {
    'binance': ('FlowNetBNBNtv', 'FlowNetBNBUSD'),
    'coinbase': ('FlowNetCBSNtv', 'FlowNetCBSUSD'),
    'okx': ('FlowNetOKXNtv', 'FlowNetOKXUSD'),
    'bybit': ('FlowNetBITNtv', 'FlowNetBITUSD'),
    'kraken': ('FlowNetKRKNtv', 'FlowNetKRKUSD'),
    'bitstamp': ('FlowNetBSPNtv', 'FlowNetBSPUSD'),
    'deribit': ('FlowNetDERNtv', 'FlowNetDERUSD'),
}


@dataclass(frozen=True)
class CoinMetricsCollectorResult:
    frames: Dict[str, pd.DataFrame]
    status: Dict[str, Any]


class CoinMetricsCommunityClient:
    """Coin Metrics Community API collector for BTC exchange flow.

    The implementation checks catalog metadata opportunistically, then requests
    only available FlowNet metrics where possible. If the catalog endpoint is not
    accessible, it falls back to requesting configured metric candidates and keeps
    successful columns only.
    """

    def __init__(self, base_url: str = 'https://community-api.coinmetrics.io/v4', timeout_seconds: float = 8.0) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'crypto-ai-system-coinmetrics-community/1.0'})

    @classmethod
    def from_config(cls, cfg: AppConfig) -> 'CoinMetricsCommunityClient':
        base = str(cfg.get('additional_data.coinmetrics.base_url', 'https://community-api.coinmetrics.io/v4'))
        timeout = float(cfg.get('additional_data.coinmetrics.timeout_seconds', cfg.get('additional_data.timeout_seconds', 8)))
        return cls(base_url=base, timeout_seconds=timeout)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(f'{self.base_url}{path}', params=params or {}, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def available_metrics(self, asset: str) -> set[str]:
        try:
            payload = self._get('/catalog-v2/asset-metrics', {'assets': asset})
        except Exception:
            return set()
        out: set[str] = set()
        for item in payload.get('data', []) or []:
            metrics = item.get('metrics') or []
            for metric in metrics:
                if isinstance(metric, dict) and metric.get('metric'):
                    out.add(str(metric.get('metric')))
                elif isinstance(metric, str):
                    out.add(metric)
        return out

    def asset_metrics(self, asset: str, metrics: Iterable[str], frequency: str, page_size: int) -> pd.DataFrame:
        metric_list = [m for m in metrics if m]
        if not metric_list:
            return pd.DataFrame()
        payload = self._get('/timeseries/asset-metrics', {
            'assets': asset,
            'metrics': ','.join(metric_list),
            'frequency': frequency,
            'page_size': page_size,
        })
        rows = []
        for item in payload.get('data', []) or []:
            row = {'timestamp': item.get('time'), 'asset': item.get('asset', asset), 'source': 'coinmetrics_community'}
            for metric in metric_list:
                row[metric] = item.get(metric)
            rows.append(row)
        return pd.DataFrame(rows)


def _configured_metric_map(cfg: AppConfig) -> dict[str, tuple[str, str]]:
    custom = cfg.get('additional_data.coinmetrics.exchange_flow_metrics')
    if not isinstance(custom, dict):
        return DEFAULT_EXCHANGE_FLOW_METRICS
    out: dict[str, tuple[str, str]] = {}
    for exchange, value in custom.items():
        if isinstance(value, dict):
            native = str(value.get('native', '') or '')
            usd = str(value.get('usd', '') or '')
            out[str(exchange)] = (native, usd)
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            out[str(exchange)] = (str(value[0]), str(value[1]))
    return out or DEFAULT_EXCHANGE_FLOW_METRICS


def collect_coinmetrics_exchange_flow(cfg: AppConfig) -> CoinMetricsCollectorResult:
    enabled = bool(cfg.get('additional_data.coinmetrics.enabled', True))
    if not enabled:
        return CoinMetricsCollectorResult(frames={}, status={'enabled': False, 'ok': True, 'source': 'coinmetrics_community'})

    client = CoinMetricsCommunityClient.from_config(cfg)
    asset = str(cfg.get('additional_data.coinmetrics.asset', 'btc')).lower()
    frequency = str(cfg.get('additional_data.coinmetrics.frequency', '1d'))
    page_size = int(cfg.get('additional_data.coinmetrics.page_size', 200))
    metric_map = _configured_metric_map(cfg)
    candidates = sorted({m for pair in metric_map.values() for m in pair if m})

    errors: Dict[str, str] = {}
    available = client.available_metrics(asset)
    metrics_to_request = [m for m in candidates if not available or m in available]

    if not metrics_to_request:
        # Coin Metrics Community catalog may be reachable while the requested
        # exchange FlowNet metrics are not available for the free asset/metric set.
        # This is an optional source, so treat it as a neutral fallback instead of
        # a pipeline failure.
        return CoinMetricsCollectorResult(
            frames={},
            status={
                'enabled': True,
                'ok': True,
                'data_available': False,
                'neutral_fallback': True,
                'source': 'coinmetrics_community',
                'requested_metrics': [],
                'candidate_metrics': candidates,
                'available_metric_count': len(available),
                'rows': 0,
                'reason': 'no_configured_exchange_flownet_metrics_available',
                'errors': errors,
            },
        )

    frame = pd.DataFrame()
    try:
        frame = client.asset_metrics(asset, metrics_to_request, frequency, page_size)
    except Exception as exc:
        errors['bulk_asset_metrics'] = str(exc)
        # Only use slower metric-by-metric fallback for API validation errors.
        # Network/timeouts should fail fast so the main trading/research cycle keeps running.
        if isinstance(exc, RequestException):
            frames = []
        else:
            frames = []
            for metric in metrics_to_request:
                try:
                    single = client.asset_metrics(asset, [metric], frequency, page_size)
                    if not single.empty:
                        frames.append(single)
                except Exception as single_exc:
                    errors[metric] = str(single_exc)
        if frames:
            frame = frames[0]
            for item in frames[1:]:
                frame = frame.merge(item, on=['timestamp', 'asset', 'source'], how='outer')

    if not frame.empty and 'timestamp' in frame.columns:
        frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
        for col in frame.columns:
            if col not in {'timestamp', 'asset', 'source'}:
                frame[col] = pd.to_numeric(frame[col], errors='coerce')
        frame = frame.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)

    return CoinMetricsCollectorResult(
        frames={'coinmetrics_exchange_flow': frame} if not frame.empty else {},
        status={
            'enabled': True,
            'ok': True if frame.empty and errors else not frame.empty,
            'data_available': not frame.empty,
            'neutral_fallback': frame.empty,
            'source': 'coinmetrics_community',
            'requested_metrics': metrics_to_request,
            'candidate_metrics': candidates,
            'available_metric_count': len(available),
            'rows': len(frame),
            'reason': None if not frame.empty else 'exchange_flow_unavailable_neutral_fallback',
            'errors': errors,
        },
    )
