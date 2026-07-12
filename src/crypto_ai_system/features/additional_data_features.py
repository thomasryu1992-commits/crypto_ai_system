from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.coinmetrics_exchange_flow_collector import DEFAULT_EXCHANGE_FLOW_METRICS


def _num(series: pd.Series | Any, default: float = 0.0) -> pd.Series | float:
    if isinstance(series, pd.Series):
        return pd.to_numeric(series, errors='coerce')
    try:
        return float(series)
    except Exception:
        return default


def _clip(value: Any, lo: float = -1.0, hi: float = 1.0) -> float:
    try:
        v = float(value)
        if pd.isna(v) or np.isinf(v):
            return 0.0
        return max(lo, min(hi, v))
    except Exception:
        return 0.0


def _zscore(s: pd.Series, window: int, min_periods: int = 5) -> pd.Series:
    values = pd.to_numeric(s, errors='coerce')
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std().replace(0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0)


def _normalize_ts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if 'timestamp' in out.columns:
        out['timestamp'] = pd.to_datetime(out['timestamp'], utc=True, errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
        out = out.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    return out


def build_binance_derivatives_features(raw_frames: Dict[str, pd.DataFrame], cfg: AppConfig | None = None) -> pd.DataFrame:
    """Merge Binance Futures public tables into one derivatives feature table."""
    frames = {k: _normalize_ts(v) for k, v in (raw_frames or {}).items() if isinstance(v, pd.DataFrame) and not v.empty}
    hist = frames.get('binance_open_interest_hist')
    if hist is None or hist.empty:
        hist = frames.get('binance_open_interest_now')
    if hist is None or hist.empty:
        return pd.DataFrame()

    out = hist.copy()
    out['open_interest'] = _num(out.get('open_interest')).ffill().fillna(0)
    if 'open_interest_value' not in out.columns:
        out['open_interest_value'] = np.nan

    merge_specs = [
        ('binance_funding_rate', ['timestamp', 'funding_rate']),
        ('binance_mark_price', ['timestamp', 'mark_price', 'index_price', 'last_funding_rate']),
        ('binance_taker_buy_sell_volume', ['timestamp', 'taker_buy_volume', 'taker_sell_volume', 'taker_buy_sell_ratio']),
        ('binance_global_long_short_ratio', ['timestamp', 'global_long_short_ratio']),
        ('binance_top_trader_account_ratio', ['timestamp', 'top_trader_account_long_short_ratio']),
        ('binance_top_trader_position_ratio', ['timestamp', 'top_trader_position_long_short_ratio']),
        ('binance_basis', ['timestamp', 'basis', 'basis_rate']),
        ('binance_orderbook_depth', ['timestamp', 'orderbook_bid_depth', 'orderbook_ask_depth', 'orderbook_imbalance', 'bid_price', 'ask_price', 'spread_bps']),
    ]
    for name, cols in merge_specs:
        frame = frames.get(name)
        if frame is not None and not frame.empty:
            keep = [c for c in cols if c in frame.columns]
            if keep and 'timestamp' in keep:
                out = out.merge(frame[keep].drop_duplicates('timestamp', keep='last'), on='timestamp', how='outer')

    out = _normalize_ts(out)
    if 'symbol' in out.columns:
        out['symbol'] = out['symbol'].ffill().bfill()
    for col in [
        'open_interest_value', 'funding_rate', 'mark_price', 'index_price', 'last_funding_rate',
        'taker_buy_volume', 'taker_sell_volume', 'taker_buy_sell_ratio', 'global_long_short_ratio',
        'top_trader_account_long_short_ratio', 'top_trader_position_long_short_ratio', 'basis', 'basis_rate',
        'orderbook_bid_depth', 'orderbook_ask_depth', 'orderbook_imbalance', 'bid_price', 'ask_price', 'spread_bps',
    ]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors='coerce')

    # Endpoint timestamps are not perfectly aligned. After the outer merge, forward-fill
    # non-price Binance fields so the latest snapshot contains the most recent known
    # taker/long-short/basis/orderbook values instead of sparse NaN columns.
    ffill_cols = [
        'open_interest_value', 'funding_rate', 'mark_price', 'index_price', 'last_funding_rate',
        'taker_buy_volume', 'taker_sell_volume', 'taker_buy_sell_ratio', 'global_long_short_ratio',
        'top_trader_account_long_short_ratio', 'top_trader_position_long_short_ratio', 'basis', 'basis_rate',
        'orderbook_bid_depth', 'orderbook_ask_depth', 'orderbook_imbalance', 'bid_price', 'ask_price', 'spread_bps',
    ]
    out[ffill_cols] = out[ffill_cols].ffill()

    out['funding_rate'] = out['funding_rate'].fillna(out['last_funding_rate']).fillna(0)
    out['open_interest'] = pd.to_numeric(out['open_interest'], errors='coerce').ffill().fillna(0)
    out['oi_change_15m'] = out['open_interest'].pct_change(1).replace([np.inf, -np.inf], np.nan).fillna(0)
    out['oi_change_1h'] = out['open_interest'].pct_change(1).replace([np.inf, -np.inf], np.nan).fillna(0)
    out['oi_change_4h'] = out['open_interest'].pct_change(4).replace([np.inf, -np.inf], np.nan).fillna(0)
    out['funding_rate_zscore'] = _zscore(out['funding_rate'], 100, 10)
    out['premium'] = ((out['mark_price'] - out['index_price']) / out['index_price'].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    buy_sell = out['taker_buy_sell_ratio'].fillna(1.0)
    top_pos = out['top_trader_position_long_short_ratio'].fillna(1.0)
    global_ls = out['global_long_short_ratio'].fillna(1.0)
    basis_rate = out['basis_rate'].fillna(out['basis']).fillna(0.0)
    orderbook_imb = out['orderbook_imbalance'].fillna(0.0)
    funding = out['funding_rate'].fillna(0.0)
    oi = out['oi_change_1h'].fillna(0.0)

    # Positive score means constructive derivatives positioning for long-side setups.
    # Negative score means either sell pressure or long-crowded risk.
    score = (
        np.clip(oi / 0.03, -1, 1) * 0.18
        + np.clip((buy_sell - 1.0) / 0.20, -1, 1) * 0.22
        + np.clip((top_pos - 1.0) / 0.30, -1, 1) * 0.18
        + np.clip((global_ls - 1.0) / 0.30, -1, 1) * 0.10
        + np.clip(orderbook_imb, -1, 1) * 0.12
        + np.clip(basis_rate / 0.0025, -1, 1) * 0.08
        - np.clip(np.abs(funding) / 0.0008, 0, 1) * 0.12
    )
    out['binance_derivatives_score'] = pd.Series(score).clip(-1, 1).fillna(0.0)
    out['derivatives_signal'] = np.where(out['binance_derivatives_score'] >= 0.35, 'BULLISH', np.where(out['binance_derivatives_score'] <= -0.35, 'BEARISH', 'NEUTRAL'))
    out['source'] = 'binance_futures_public_features'
    return out.reset_index(drop=True)


def build_exchange_flow_features(raw: pd.DataFrame, cfg: AppConfig | None = None) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    out = _normalize_ts(raw)
    metric_map = DEFAULT_EXCHANGE_FLOW_METRICS
    custom = cfg.get('additional_data.coinmetrics.exchange_flow_metrics') if cfg else None
    if isinstance(custom, dict):
        metric_map = {}
        for ex, spec in custom.items():
            if isinstance(spec, dict):
                metric_map[str(ex)] = (str(spec.get('native', '') or ''), str(spec.get('usd', '') or ''))
            elif isinstance(spec, (list, tuple)) and len(spec) >= 2:
                metric_map[str(ex)] = (str(spec[0]), str(spec[1]))

    native_cols = []
    usd_cols = []
    for exchange, (native_metric, usd_metric) in metric_map.items():
        ex = str(exchange).lower()
        native_name = f'btc_{ex}_netflow'
        usd_name = f'btc_{ex}_netflow_usd'
        if native_metric in out.columns:
            out[native_name] = pd.to_numeric(out[native_metric], errors='coerce')
            native_cols.append(native_name)
        else:
            out[native_name] = np.nan
        if usd_metric in out.columns:
            out[usd_name] = pd.to_numeric(out[usd_metric], errors='coerce')
            usd_cols.append(usd_name)
        else:
            out[usd_name] = np.nan

    out['btc_exchange_netflow'] = out[native_cols].sum(axis=1, min_count=1) if native_cols else np.nan
    out['btc_exchange_netflow_usd'] = out[usd_cols].sum(axis=1, min_count=1) if usd_cols else np.nan
    out['exchange_netflow_ma_7d'] = out['btc_exchange_netflow'].rolling(7, min_periods=2).mean()
    out['exchange_netflow_ma_30d'] = out['btc_exchange_netflow'].rolling(30, min_periods=5).mean()
    out['exchange_netflow_zscore_30d'] = _zscore(out['btc_exchange_netflow'], 30, 5)

    # Positive exchange netflow = possible sell pressure. Negative netflow = possible accumulation.
    score = -np.clip(out['exchange_netflow_zscore_30d'] / 2.0, -1, 1)
    out['exchange_flow_score'] = pd.Series(score).fillna(0.0).clip(-1, 1)
    out['netflow_signal'] = np.where(out['exchange_flow_score'] >= 0.35, 'ACCUMULATION', np.where(out['exchange_flow_score'] <= -0.35, 'SELL_PRESSURE', 'NEUTRAL'))
    out['source'] = 'coinmetrics_exchange_flow_features'
    return out.reset_index(drop=True)


def build_etf_flow_features(raw: pd.DataFrame, cfg: AppConfig | None = None) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    out = _normalize_ts(raw)
    for col in ['total_flow_usd_m', 'ibit_flow_usd_m', 'fbtc_flow_usd_m', 'gbtc_flow_usd_m', 'other_etf_flow_usd_m']:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors='coerce')
    out['etf_flow_5d_sum'] = out['total_flow_usd_m'].rolling(5, min_periods=1).sum()
    out['etf_flow_20d_sum'] = out['total_flow_usd_m'].rolling(20, min_periods=1).sum()
    out['etf_flow_20d_zscore'] = _zscore(out['total_flow_usd_m'], 20, 5)
    directional = np.clip(out['etf_flow_5d_sum'] / 1000.0, -1, 1)
    unusual = np.clip(out['etf_flow_20d_zscore'] / 2.5, -1, 1) * 0.35
    out['etf_flow_score'] = (directional * 0.65 + unusual).clip(-1, 1).fillna(0.0)
    out['etf_signal'] = np.where(out['etf_flow_score'] >= 0.35, 'INFLOW_SUPPORT', np.where(out['etf_flow_score'] <= -0.35, 'OUTFLOW_PRESSURE', 'NEUTRAL'))
    out['source'] = 'farside_etf_flow_features'
    return out.reset_index(drop=True)


def build_stablecoin_liquidity_features(raw_frames: Dict[str, pd.DataFrame], cfg: AppConfig | None = None) -> pd.DataFrame:
    current = raw_frames.get('defillama_stablecoins_current') if raw_frames else None
    charts = raw_frames.get('defillama_stablecoin_charts_all') if raw_frames else None
    rows = []
    if current is not None and not current.empty:
        cur = current.copy()
        cur['mcap_usd'] = pd.to_numeric(cur.get('mcap_usd'), errors='coerce')
        ts = str(cur.get('timestamp', pd.Series([pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S+00:00')])).iloc[-1])
        total = cur['mcap_usd'].sum(skipna=True)
        usdt = cur.loc[cur['stablecoin_symbol'].astype(str).str.upper().eq('USDT'), 'mcap_usd'].sum(skipna=True)
        usdc = cur.loc[cur['stablecoin_symbol'].astype(str).str.upper().eq('USDC'), 'mcap_usd'].sum(skipna=True)
        rows.append({'timestamp': ts, 'stablecoin_total_mcap': total, 'usdt_mcap': usdt, 'usdc_mcap': usdc, 'source': 'defillama_stablecoins_features'})

    if charts is not None and not charts.empty:
        ch = _normalize_ts(charts)
        if 'stablecoin_total_mcap' in ch.columns:
            ch['stablecoin_total_mcap'] = pd.to_numeric(ch['stablecoin_total_mcap'], errors='coerce')
            for _, item in ch.iterrows():
                rows.append({'timestamp': item['timestamp'], 'stablecoin_total_mcap': item.get('stablecoin_total_mcap'), 'usdt_mcap': np.nan, 'usdc_mcap': np.nan, 'source': 'defillama_stablecoins_features'})

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = _normalize_ts(out).drop_duplicates('timestamp', keep='last').sort_values('timestamp').reset_index(drop=True)
    for col in ['stablecoin_total_mcap', 'usdt_mcap', 'usdc_mcap']:
        out[col] = pd.to_numeric(out[col], errors='coerce').ffill()
    out['stablecoin_total_mcap_7d_change'] = out['stablecoin_total_mcap'].pct_change(7, fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0)
    out['stablecoin_total_mcap_30d_change'] = out['stablecoin_total_mcap'].pct_change(30, fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0)

    # /stablecoincharts/all provides total market cap history. The current endpoint
    # provides USDT/USDC current supply, but not a full symbol-level history. Keep
    # USDT/USDC change as NaN unless enough historical points exist; scoring treats
    # missing component data as neutral instead of incorrectly reporting 0% change.
    usdt_change = out['usdt_mcap'].pct_change(7, fill_method=None).replace([np.inf, -np.inf], np.nan)
    usdc_change = out['usdc_mcap'].pct_change(7, fill_method=None).replace([np.inf, -np.inf], np.nan)
    if out['usdt_mcap'].notna().sum() < 8:
        usdt_change = pd.Series(np.nan, index=out.index)
    if out['usdc_mcap'].notna().sum() < 8:
        usdc_change = pd.Series(np.nan, index=out.index)
    out['usdt_7d_change'] = usdt_change
    out['usdc_7d_change'] = usdc_change

    out['stablecoin_liquidity_score'] = (
        np.clip(out['stablecoin_total_mcap_7d_change'] / 0.01, -1, 1) * 0.55
        + np.clip(out['stablecoin_total_mcap_30d_change'] / 0.03, -1, 1) * 0.30
        + np.clip(out['usdc_7d_change'].fillna(0) / 0.015, -1, 1) * 0.15
    ).clip(-1, 1).fillna(0.0)
    return out.reset_index(drop=True)


def latest_feature_dict(frame: pd.DataFrame, prefix: str | None = None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    row = frame.iloc[-1].replace({np.nan: None}).to_dict()
    if not prefix:
        return row
    return {f'{prefix}_{k}': v for k, v in row.items() if k != 'timestamp'} | {f'{prefix}_timestamp': row.get('timestamp')}


def build_additional_feature_frames(raw_frames: Dict[str, pd.DataFrame], cfg: AppConfig) -> Dict[str, pd.DataFrame]:
    features: Dict[str, pd.DataFrame] = {}
    binance = build_binance_derivatives_features(raw_frames, cfg)
    if not binance.empty:
        features['binance_derivatives_features'] = binance
    exchange = build_exchange_flow_features(raw_frames.get('coinmetrics_exchange_flow', pd.DataFrame()), cfg)
    if not exchange.empty:
        features['exchange_flow_features'] = exchange
    etf = build_etf_flow_features(raw_frames.get('farside_btc_etf_flow', pd.DataFrame()), cfg)
    if not etf.empty:
        features['etf_flow_features'] = etf
    stable = build_stablecoin_liquidity_features(raw_frames, cfg)
    if not stable.empty:
        features['stablecoin_liquidity_features'] = stable
    return features


def build_additional_feature_snapshot(feature_frames: Dict[str, pd.DataFrame]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for name, frame in (feature_frames or {}).items():
        if frame is None or frame.empty:
            continue
        row = frame.iloc[-1].replace({np.nan: None}).to_dict()
        for key, value in row.items():
            if key == 'timestamp':
                snapshot[f'{name}_timestamp'] = value
            elif key not in snapshot:
                snapshot[key] = value
            else:
                snapshot[f'{name}_{key}'] = value
    return snapshot
