from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


REQUIRED_OHLCV_COLUMNS = ['timestamp', 'symbol', 'exchange', 'exchange_market', 'timeframe', 'open', 'high', 'low', 'close', 'volume', 'source']
REQUIRED_DERIVATIVE_COLUMNS = ['timestamp', 'symbol', 'exchange', 'exchange_market', 'timeframe', 'funding_rate', 'open_interest', 'source']
NUMERIC_OHLCV_COLUMNS = ['open', 'high', 'low', 'close', 'volume']
NUMERIC_DERIVATIVE_COLUMNS = ['funding_rate', 'open_interest', 'open_interest_base', 'oi_change_pct', 'long_liquidation', 'short_liquidation']


@dataclass(frozen=True)
class DataContractReport:
    name: str
    ok: bool
    rows: int
    missing_columns: list[str]
    null_columns: list[str]
    duplicate_rows: int
    latest_timestamp: str | None
    problems: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_timestamp_column(df: pd.DataFrame) -> pd.Series:
    ts = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    return ts.dt.strftime('%Y-%m-%d %H:%M:%S%z').str.replace(r'(\+0000)$', '+00:00', regex=True)


def validate_and_normalize_frame(df: pd.DataFrame, *, name: str, required: list[str], numeric: list[str]) -> tuple[pd.DataFrame, DataContractReport]:
    frame = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    missing = [c for c in required if c not in frame.columns]
    problems: list[str] = []
    if missing:
        problems.append('MISSING_REQUIRED_COLUMNS')
        for c in missing:
            frame[c] = pd.NA

    if 'timestamp' in frame.columns:
        frame['timestamp'] = _normalize_timestamp_column(frame)
    for c in numeric:
        if c in frame.columns:
            frame[c] = pd.to_numeric(frame[c], errors='coerce')

    if 'symbol' in frame.columns:
        frame['symbol'] = frame['symbol'].astype(str)
    if 'source' in frame.columns:
        frame['source'] = frame['source'].astype(str)

    null_cols = [c for c in required if c in frame.columns and frame[c].isna().any()]
    if null_cols:
        problems.append('NULL_REQUIRED_VALUES')

    keys = [c for c in ['timestamp', 'symbol', 'exchange_market', 'timeframe', 'source'] if c in frame.columns]
    duplicates = int(frame.duplicated(subset=keys).sum()) if keys else 0
    if duplicates:
        problems.append('DUPLICATE_ROWS')

    if 'timestamp' in frame.columns:
        frame = frame.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)

    latest = str(frame['timestamp'].iloc[-1]) if not frame.empty and 'timestamp' in frame.columns else None
    ok = not missing and not null_cols and duplicates == 0 and not frame.empty
    report = DataContractReport(name=name, ok=ok, rows=int(len(frame)), missing_columns=missing, null_columns=null_cols, duplicate_rows=duplicates, latest_timestamp=latest, problems=problems)
    return frame, report


def validate_ohlcv(df: pd.DataFrame, *, name: str = 'ohlcv') -> tuple[pd.DataFrame, DataContractReport]:
    return validate_and_normalize_frame(df, name=name, required=REQUIRED_OHLCV_COLUMNS, numeric=NUMERIC_OHLCV_COLUMNS)


def validate_derivatives(df: pd.DataFrame, *, name: str = 'derivatives') -> tuple[pd.DataFrame, DataContractReport]:
    return validate_and_normalize_frame(df, name=name, required=REQUIRED_DERIVATIVE_COLUMNS, numeric=NUMERIC_DERIVATIVE_COLUMNS)
