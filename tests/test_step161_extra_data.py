from __future__ import annotations

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.features.additional_data_features import (
    build_binance_derivatives_features,
    build_exchange_flow_features,
    build_etf_flow_features,
    build_stablecoin_liquidity_features,
)
from crypto_ai_system.analysis.score_engine import ScoreEngine


def test_binance_derivatives_feature_score() -> None:
    raw = {
        'binance_open_interest_hist': pd.DataFrame([
            {'timestamp': '2026-06-01 00:00:00+00:00', 'symbol': 'BTCUSDT', 'open_interest': 100, 'open_interest_value': 1000},
            {'timestamp': '2026-06-01 01:00:00+00:00', 'symbol': 'BTCUSDT', 'open_interest': 104, 'open_interest_value': 1040},
        ]),
        'binance_taker_buy_sell_volume': pd.DataFrame([
            {'timestamp': '2026-06-01 01:00:00+00:00', 'symbol': 'BTCUSDT', 'taker_buy_sell_ratio': 1.2, 'taker_buy_volume': 120, 'taker_sell_volume': 100},
        ]),
        'binance_top_trader_position_ratio': pd.DataFrame([
            {'timestamp': '2026-06-01 01:00:00+00:00', 'symbol': 'BTCUSDT', 'top_trader_position_long_short_ratio': 1.25},
        ]),
    }
    frame = build_binance_derivatives_features(raw)
    assert not frame.empty
    assert 'binance_derivatives_score' in frame.columns
    assert frame['binance_derivatives_score'].iloc[-1] > 0


def test_exchange_flow_positive_netflow_is_sell_pressure() -> None:
    cfg = load_config('.')
    raw = pd.DataFrame([
        {'timestamp': f'2026-06-{i+1:02d} 00:00:00+00:00', 'asset': 'btc', 'FlowNetBNBNtv': i * 10, 'FlowNetBNBUSD': i * 1000, 'source': 'coinmetrics_community'}
        for i in range(35)
    ])
    frame = build_exchange_flow_features(raw, cfg)
    assert not frame.empty
    assert 'exchange_flow_score' in frame.columns
    assert frame['exchange_flow_score'].iloc[-1] < 0


def test_etf_and_stablecoin_features_emit_scores() -> None:
    etf_raw = pd.DataFrame([
        {'timestamp': f'2026-06-{i+1:02d} 00:00:00+00:00', 'total_flow_usd_m': 100, 'ibit_flow_usd_m': 80, 'fbtc_flow_usd_m': 20, 'gbtc_flow_usd_m': 0}
        for i in range(10)
    ])
    etf = build_etf_flow_features(etf_raw)
    assert etf['etf_flow_score'].iloc[-1] > 0

    stable_raw = {
        'defillama_stablecoin_charts_all': pd.DataFrame([
            {'timestamp': f'2026-06-{i+1:02d} 00:00:00+00:00', 'stablecoin_total_mcap': 100_000_000_000 + i * 200_000_000, 'source': 'defillama'}
            for i in range(40)
        ])
    }
    stable = build_stablecoin_liquidity_features(stable_raw)
    assert 'stablecoin_liquidity_score' in stable.columns
    assert stable['stablecoin_liquidity_score'].iloc[-1] > 0


def test_score_engine_contains_extra_components() -> None:
    engine = ScoreEngine()
    score = engine.score_row({
        'close': 105,
        'ma20': 100,
        'ma50': 95,
        'rsi': 60,
        'adx': 25,
        'oi_change_pct': 0.01,
        'funding_zscore': 0,
        'mark_index_basis_bps': 5,
        'liquidation_imbalance': 0,
        'atr_pct_of_price': 0.01,
        'spread_bps': 2,
        'exchange_flow_score': 0.4,
        'etf_flow_score': 0.5,
        'stablecoin_liquidity_score': 0.2,
    }).to_dict()
    assert 'exchange_flow' in score
    assert 'etf_flow' in score
    assert 'stablecoin_liquidity' in score
    assert score['total_score'] > 0


def test_binance_derivatives_forward_fills_sparse_endpoint_rows() -> None:
    raw = {
        'binance_open_interest_hist': pd.DataFrame([
            {'timestamp': '2026-06-01 00:00:00+00:00', 'symbol': 'BTCUSDT', 'open_interest': 100},
            {'timestamp': '2026-06-01 01:00:00+00:00', 'symbol': 'BTCUSDT', 'open_interest': 101},
        ]),
        'binance_taker_buy_sell_volume': pd.DataFrame([
            {'timestamp': '2026-06-01 01:00:00+00:00', 'symbol': 'BTCUSDT', 'taker_buy_sell_ratio': 1.15, 'taker_buy_volume': 115, 'taker_sell_volume': 100},
        ]),
        'binance_orderbook_depth': pd.DataFrame([
            {'timestamp': '2026-06-01 01:00:05+00:00', 'symbol': 'BTCUSDT', 'orderbook_bid_depth': 10, 'orderbook_ask_depth': 9, 'orderbook_imbalance': 0.05},
        ]),
    }
    frame = build_binance_derivatives_features(raw)
    latest = frame.iloc[-1]
    assert latest['taker_buy_sell_ratio'] == 1.15
    assert latest['orderbook_imbalance'] == 0.05
    assert latest['symbol'] == 'BTCUSDT'


def test_stablecoin_symbol_level_changes_are_nan_without_history() -> None:
    stable_raw = {
        'defillama_stablecoin_charts_all': pd.DataFrame([
            {'timestamp': f'2026-06-{i+1:02d} 00:00:00+00:00', 'stablecoin_total_mcap': 100_000_000_000 + i * 100_000_000, 'source': 'defillama'}
            for i in range(10)
        ]),
        'defillama_stablecoins_current': pd.DataFrame([
            {'timestamp': '2026-06-11 00:00:00+00:00', 'stablecoin_symbol': 'USDT', 'mcap_usd': 180_000_000_000},
            {'timestamp': '2026-06-11 00:00:00+00:00', 'stablecoin_symbol': 'USDC', 'mcap_usd': 70_000_000_000},
        ]),
    }
    frame = build_stablecoin_liquidity_features(stable_raw)
    latest = frame.iloc[-1]
    assert pd.isna(latest['usdt_7d_change'])
    assert pd.isna(latest['usdc_7d_change'])
    assert 'stablecoin_liquidity_score' in frame.columns
