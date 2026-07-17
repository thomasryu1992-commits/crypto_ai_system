from __future__ import annotations

from typing import Any, Tuple

import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.coinalyze_client import CoinalyzeClient
from crypto_ai_system.data.data_contract import validate_derivatives, validate_ohlcv
from crypto_ai_system.data.extended_client import ExtendedClient
from crypto_ai_system.data.mock_data import generate_mock_derivatives, generate_mock_mark_index, generate_mock_ohlcv
from crypto_ai_system.data.price_data_loader import (
    build_derivatives_from_price_data,
    load_price_history_bundle,
    select_primary_ohlcv_from_price_bundle,
)
from crypto_ai_system.data.symbol_mapper import get_coinalyze_symbol, get_market_identity
from core.event_log import log_event
from crypto_ai_system.storage.paths import ensure_storage_dirs



def _active_fallback_profile(cfg: AppConfig) -> dict[str, Any]:
    profiles = cfg.get('fallback_data_profiles.profiles', {}) or {}
    profile_id = str(cfg.get('data.fallback_profile', cfg.get('fallback_data_profiles.default_profile', 'price_data_research')))
    profile = dict(profiles.get(profile_id, {}) or {})
    if not profile:
        profile = {
            'profile_id': profile_id,
            'source': profile_id,
            'role': 'RESEARCH_BACKTEST_ONLY',
            'allow_live_execution': False,
            'allow_paper_order_execution': False,
            'use_for_ohlcv': True,
            'use_for_derivatives_proxy': True,
        }
    profile.setdefault('profile_id', profile_id)
    profile.setdefault('role', 'RESEARCH_BACKTEST_ONLY')
    profile.setdefault('allow_live_execution', False)
    profile.setdefault('allow_paper_order_execution', False)
    return profile


def _try_collect_extended(cfg: AppConfig, limit: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, str]:
    market = get_market_identity(cfg)
    client = ExtendedClient.from_config(cfg)
    candle_type = str(cfg.get('data.extended_candle_type', 'trades'))
    ohlcv = client.get_candles(market=market, candle_type=candle_type, limit=limit)
    mark = client.get_candles(market=market, candle_type='mark-prices', limit=limit)
    index = client.get_candles(market=market, candle_type='index-prices', limit=limit)
    derivatives = client.get_derivatives(
        market=market,
        limit=limit,
        funding_hours=int(cfg.get('extended.funding_lookback_hours', limit)),
        oi_hours=int(cfg.get('extended.oi_lookback_hours', min(limit, 300))),
    )
    try:
        orderbook = client.get_orderbook_snapshot(market)
        orderbook['source'] = 'extended'
    except Exception as exc:
        orderbook = {'bid_price': None, 'ask_price': None, 'spread_bps': None, 'source': 'extended_orderbook_error', 'error': str(exc)}
    return ohlcv, derivatives, mark, index, orderbook, 'extended'


def _try_collect_coinalyze(cfg: AppConfig, limit: int) -> pd.DataFrame:
    market = get_market_identity(cfg)
    symbol = get_coinalyze_symbol(cfg)
    interval = str(cfg.get('coinalyze.interval', '1hour'))
    coi = CoinalyzeClient(api_key=cfg.get('coinalyze.api_key')).get_derivatives_if_configured(symbol=symbol, interval=interval, limit=limit)
    if coi is None or coi.empty:
        return pd.DataFrame()
    out = coi.copy()
    out['symbol'] = market.canonical_symbol
    out['exchange'] = 'coinalyze'
    out['exchange_market'] = symbol
    out['timeframe'] = market.timeframe
    out['source'] = 'coinalyze'
    return out


def _merge_derivatives(primary: pd.DataFrame, enrichment: pd.DataFrame) -> pd.DataFrame:
    if enrichment is None or enrichment.empty:
        return primary
    if primary is None or primary.empty:
        return enrichment

    left = primary.copy()
    right = enrichment.copy()
    left['timestamp'] = left['timestamp'].astype(str)
    right['timestamp'] = right['timestamp'].astype(str)
    merged = left.merge(right, on='timestamp', how='outer', suffixes=('', '_coinalyze'))
    for col in ['funding_rate', 'open_interest', 'open_interest_base', 'oi_change_pct', 'long_liquidation', 'short_liquidation', 'long_short_ratio']:
        c2 = f'{col}_coinalyze'
        if c2 in merged.columns:
            if col in merged.columns:
                merged[col] = pd.to_numeric(merged[c2], errors='coerce').combine_first(pd.to_numeric(merged[col], errors='coerce'))
            else:
                merged[col] = merged[c2]
    for col in ['symbol', 'exchange', 'exchange_market', 'timeframe']:
        c2 = f'{col}_coinalyze'
        if col not in merged.columns and c2 in merged.columns:
            merged[col] = merged[c2]
        elif col in merged.columns:
            merged[col] = merged[col].fillna(merged.get(c2)) if c2 in merged.columns else merged[col]
    merged['source'] = 'extended+coinalyze'
    drop_cols = [c for c in merged.columns if c.endswith('_coinalyze')]
    return merged.drop(columns=drop_cols).sort_values('timestamp').reset_index(drop=True)


def collect_market_data(cfg: AppConfig) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    ohlcv, derivatives, _mark, _index, _orderbook, source = collect_extended_market_bundle(cfg)
    return ohlcv, derivatives, source


def collect_extended_market_bundle(cfg: AppConfig) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, str]:
    paths = ensure_storage_dirs(cfg)
    market = get_market_identity(cfg)
    limit = int(cfg.get('data.limit', 500))
    allow_fallback = bool(cfg.get('data.allow_sample_fallback', True))
    use_coinalyze = bool(cfg.get('data.use_coinalyze_enrichment', True)) and bool(cfg.get('coinalyze.enabled', True))
    fallback_profile = _active_fallback_profile(cfg)
    contract_reports: list[dict[str, Any]] = []

    try:
        ohlcv, derivatives, mark, index, orderbook, source = _try_collect_extended(cfg, limit)
        log_event('data_collect', {'source': 'extended', 'rows': len(ohlcv), 'market': market.exchange_market})
    except Exception as exc:
        if not allow_fallback:
            raise

        price_bundle = load_price_history_bundle(cfg)
        use_price_fallback = bool(cfg.get('price_data.use_as_fallback_for_ohlcv', True)) and bool(fallback_profile.get('use_for_ohlcv', True))
        price_ohlcv = select_primary_ohlcv_from_price_bundle(cfg, price_bundle) if use_price_fallback else pd.DataFrame()

        if not price_ohlcv.empty:
            ohlcv = price_ohlcv.tail(limit).reset_index(drop=True)
            ohlcv['symbol'] = market.canonical_symbol
            ohlcv['exchange'] = 'binance'
            ohlcv['exchange_market'] = 'BTCUSDT.P'
            ohlcv['timeframe'] = market.timeframe
            ohlcv['source'] = 'price_data_binance_tradingview'
            mark, index = generate_mock_mark_index(ohlcv)
            mark['source'] = 'price_data_mark_proxy'
            index['source'] = 'price_data_index_proxy'
            derivatives = build_derivatives_from_price_data(ohlcv, cfg)
            orderbook = {
                'bid_price': float(ohlcv.iloc[-1]['close']) * 0.9998,
                'ask_price': float(ohlcv.iloc[-1]['close']) * 1.0002,
                'spread_bps': 4.0,
                'source': 'price_data_proxy',
            }
            source = str(fallback_profile.get('source') or 'price_data_binance_tradingview')
            orderbook['fallback_profile_id'] = fallback_profile.get('profile_id')
            orderbook['fallback_profile_role'] = fallback_profile.get('role')
            orderbook['fallback_allows_live_execution'] = bool(fallback_profile.get('allow_live_execution', False))
            log_event('data_collect_fallback', {
                'source': source,
                'reason': str(exc),
                'rows': len(ohlcv),
                'price_timeframes_loaded': sorted(price_bundle.keys()),
                'fallback_profile_id': fallback_profile.get('profile_id'),
                'fallback_profile_role': fallback_profile.get('role'),
                'fallback_allows_live_execution': bool(fallback_profile.get('allow_live_execution', False)),
            })
        else:
            ohlcv = generate_mock_ohlcv(symbol=market.canonical_symbol, timeframe=market.timeframe, periods=limit)
            ohlcv['exchange_market'] = market.exchange_market
            mark, index = generate_mock_mark_index(ohlcv)
            derivatives = generate_mock_derivatives(ohlcv)
            orderbook = {'bid_price': float(ohlcv.iloc[-1]['close']) * 0.9998, 'ask_price': float(ohlcv.iloc[-1]['close']) * 1.0002, 'spread_bps': 4.0, 'source': 'sample_proxy'}
            source = 'sample_extended'
            sample_profile = dict((cfg.get('fallback_data_profiles.profiles.sample_extended_research', {}) or {}))
            orderbook['fallback_profile_id'] = sample_profile.get('profile_id', 'sample_extended_research')
            orderbook['fallback_profile_role'] = sample_profile.get('role', 'RESEARCH_BACKTEST_ONLY')
            orderbook['fallback_allows_live_execution'] = bool(sample_profile.get('allow_live_execution', False))
            log_event('data_collect_fallback', {'source': 'sample_extended', 'reason': str(exc), 'rows': len(ohlcv), 'fallback_profile_id': sample_profile.get('profile_id', 'sample_extended_research'), 'fallback_profile_role': sample_profile.get('role', 'RESEARCH_BACKTEST_ONLY'), 'fallback_allows_live_execution': bool(sample_profile.get('allow_live_execution', False))})

    ohlcv, report = validate_ohlcv(ohlcv, name=f'{source}_ohlcv')
    contract_reports.append(report.to_dict())
    derivatives, report = validate_derivatives(derivatives, name=f'{source}_derivatives')
    contract_reports.append(report.to_dict())

    coinalyze_rows = 0
    if use_coinalyze:
        try:
            coi = _try_collect_coinalyze(cfg, limit)
            if coi is not None and not coi.empty:
                coi, coi_report = validate_derivatives(coi, name='coinalyze_derivatives')
                contract_reports.append(coi_report.to_dict())
                derivatives = _merge_derivatives(derivatives, coi)
                coinalyze_rows = len(coi)
                log_event('data_collect_enrichment', {'source': 'coinalyze', 'rows': coinalyze_rows})
        except Exception as exc:
            log_event('data_collect_enrichment_skipped', {'source': 'coinalyze', 'reason': str(exc)})

    orderbook = dict(orderbook or {})
    orderbook['coinalyze_rows'] = coinalyze_rows
    orderbook['data_contract_reports'] = contract_reports

    return (
        ohlcv.reset_index(drop=True),
        derivatives.reset_index(drop=True),
        mark.reset_index(drop=True),
        index.reset_index(drop=True),
        orderbook,
        source,
    )
