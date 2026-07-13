from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from crypto_ai_system.config import AppConfig


@dataclass(frozen=True)
class FarsideCollectorResult:
    frames: Dict[str, pd.DataFrame]
    status: Dict[str, Any]


def _clean_col(name: Any) -> str:
    text = str(name).strip().lower()
    return ''.join(ch if ch.isalnum() else '_' for ch in text).strip('_')


def _to_usd_m(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(',', '').replace('$', '')
    if text in {'', '-', 'nan', 'None'}:
        return None
    multiplier = 1.0
    if text.lower().endswith('bn') or text.lower().endswith('b'):
        multiplier = 1000.0
        text = text.rstrip('BbNn')
    elif text.lower().endswith('mn') or text.lower().endswith('m'):
        multiplier = 1.0
        text = text.rstrip('MmNn')
    try:
        return float(text) * multiplier
    except Exception:
        return None


def _first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(df.columns)
    for candidate in candidates:
        if candidate in cols:
            return candidate
    return None


def read_farside_btc_etf_flow_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    raw = pd.read_csv(path)
    raw.columns = [_clean_col(c) for c in raw.columns]
    date_col = _first_existing(raw, ['date', 'day', 'timestamp', 'time'])
    if not date_col:
        return pd.DataFrame()

    total_col = _first_existing(raw, ['total', 'total_flow', 'total_daily_flow', 'total_net_flow', 'total_usd_m', 'total_flow_usd_m'])
    ibit_col = _first_existing(raw, ['ibit', 'blackrock', 'blackrock_ibit', 'ibit_flow', 'ibit_usd_m'])
    fbtc_col = _first_existing(raw, ['fbtc', 'fidelity', 'fidelity_fbtc', 'fbtc_flow', 'fbtc_usd_m'])
    gbtc_col = _first_existing(raw, ['gbtc', 'grayscale', 'grayscale_gbtc', 'gbtc_flow', 'gbtc_usd_m'])

    out = pd.DataFrame()
    out['timestamp'] = pd.to_datetime(raw[date_col], utc=True, errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
    out['date'] = pd.to_datetime(raw[date_col], errors='coerce').dt.date.astype(str)
    out['total_flow_usd_m'] = raw[total_col].map(_to_usd_m) if total_col else None
    out['ibit_flow_usd_m'] = raw[ibit_col].map(_to_usd_m) if ibit_col else None
    out['fbtc_flow_usd_m'] = raw[fbtc_col].map(_to_usd_m) if fbtc_col else None
    out['gbtc_flow_usd_m'] = raw[gbtc_col].map(_to_usd_m) if gbtc_col else None
    major = out[['ibit_flow_usd_m', 'fbtc_flow_usd_m', 'gbtc_flow_usd_m']].sum(axis=1, min_count=1)
    out['other_etf_flow_usd_m'] = out['total_flow_usd_m'] - major
    out['source'] = 'farside_manual_csv'
    return out.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)


def collect_farside_etf_flow(cfg: AppConfig) -> FarsideCollectorResult:
    enabled = bool(cfg.get('additional_data.farside.enabled', True))
    if not enabled:
        return FarsideCollectorResult(frames={}, status={'enabled': False, 'ok': True, 'source': 'farside_etf_flow'})

    configured = cfg.get('additional_data.farside.csv_path', 'data/raw/etf/farside_btc_etf_flow.csv')
    path = Path(str(configured))
    if not path.is_absolute():
        path = cfg.root / path
    frame = read_farside_btc_etf_flow_csv(path)
    return FarsideCollectorResult(
        frames={'farside_btc_etf_flow': frame} if not frame.empty else {},
        status={
            'enabled': True,
            'ok': not frame.empty,
            'source': 'farside_etf_flow',
            'mode': 'manual_csv',
            'csv_path': str(path),
            'rows': len(frame),
            'errors': {} if path.exists() else {'manual_csv': f'CSV_NOT_FOUND:{path}'},
        },
    )
