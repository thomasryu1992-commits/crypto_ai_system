from __future__ import annotations

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.features.research_feature_matrix import build_research_feature_matrix
from crypto_ai_system.research.research_signal_builder import build_research_signal


def test_research_feature_matrix_asof_merges_extra_data() -> None:
    cfg = load_config('.')
    base = pd.DataFrame([
        {'timestamp': '2026-06-01 00:00:00+00:00', 'close': 100, 'ma20': 99, 'ma50': 98},
        {'timestamp': '2026-06-01 01:00:00+00:00', 'close': 101, 'ma20': 99, 'ma50': 98},
    ])
    extra = {
        'exchange_flow_features': pd.DataFrame([
            {'timestamp': '2026-06-01 00:30:00+00:00', 'exchange_flow_score': 0.4, 'exchange_netflow_zscore_30d': -1.2},
        ]),
        'etf_flow_features': pd.DataFrame([
            {'timestamp': '2026-06-01 00:00:00+00:00', 'etf_flow_score': 0.5, 'etf_flow_5d_sum': 700},
        ]),
    }
    matrix = build_research_feature_matrix(base, extra, cfg)
    assert len(matrix) == 2
    assert matrix['exchange_flow_score'].iloc[-1] == 0.4
    assert matrix['etf_flow_score'].iloc[-1] == 0.5
    assert 'stablecoin_liquidity_score' in matrix.columns
    assert matrix['stablecoin_liquidity_score'].iloc[-1] == 0.0
    assert matrix['feature_matrix_version'].iloc[-1] == 'step259_weight_calibration_permission_distribution_matrix'


def test_research_signal_v2_allows_reduced_risk_permission() -> None:
    cfg = load_config('.')
    snapshot = {
        'timestamp': '2026-06-01 01:00:00+00:00',
        'symbol': 'BTC-PERP',
        'timeframe': 'PT1H',
        'exchange_market': 'BTC-USD',
        'data_quality_status': 'OK',
        'close': 100000,
        'score_total_score': 0.72,
        'score_bias': 'BULLISH',
        'score_structure': 0.8,
        'score_momentum': 0.4,
        'score_derivatives': 0.3,
        'score_exchange_flow': 0.2,
        'score_etf_flow': 0.2,
        'score_stablecoin_liquidity': 0.1,
        'score_risk': -0.10,
        'market_regime': 'TREND_UP',
        'market_condition': 'BULLISH_TREND_OPPORTUNITY',
        'mtf_bias': 'BULLISH',
        'mtf_alignment_score': 0.5,
        'spread_bps': 2,
        'funding_rate': 0.0006,
        'oi_change_pct': 0.02,
        'binance_derivatives_score': 0.30,
        'exchange_flow_score': 0.10,
        'etf_flow_score': 0.20,
        'stablecoin_liquidity_score': 0.10,
    }
    signal = build_research_signal(snapshot, {'final_condition': 'BULLISH_TREND_OPPORTUNITY'}, cfg, source='extended')
    assert signal['version'] == 'research_signal_v2_step259_weight_calibration_permission_distribution'
    assert signal['entry_side'] == 'LONG'
    assert signal['entry_allowed'] is True
    assert signal['trade_permission']['allow_long'] is True
    assert signal['trade_permission']['risk_level'] == 'reduced'
    assert 'FUNDING_ELEVATED_REDUCE_SIZE' in signal['trade_permission']['risk_warnings']


def test_research_signal_v2_blocks_directional_long_on_exchange_sell_pressure() -> None:
    cfg = load_config('.')
    snapshot = {
        'timestamp': '2026-06-01 01:00:00+00:00',
        'symbol': 'BTC-PERP',
        'timeframe': 'PT1H',
        'exchange_market': 'BTC-USD',
        'data_quality_status': 'OK',
        'close': 100000,
        'score_total_score': 0.72,
        'score_bias': 'BULLISH',
        'market_regime': 'TREND_UP',
        'market_condition': 'BULLISH_TREND_OPPORTUNITY',
        'spread_bps': 2,
        'funding_rate': 0.0001,
        'oi_change_pct': 0.01,
        'binance_derivatives_score': 0.20,
        'exchange_flow_score': -0.70,
        'etf_flow_score': 0.10,
        'stablecoin_liquidity_score': 0.10,
    }
    signal = build_research_signal(snapshot, {'final_condition': 'BULLISH_TREND_OPPORTUNITY'}, cfg, source='extended')
    assert signal['entry_side'] == 'LONG'
    assert signal['entry_allowed'] is False
    assert signal['trade_permission']['risk_level'] == 'blocked'
    assert 'LONG_BLOCKED_BY_EXCHANGE_SELL_PRESSURE' in signal['block_reasons']


def test_research_feature_matrix_no_suffix_leakage_when_base_has_neutral_extra_columns() -> None:
    cfg = load_config('.')
    base = pd.DataFrame([
        {
            'timestamp': '2026-06-01 01:00:00+00:00',
            'close': 101,
            'ma20': 99,
            'ma50': 98,
            'binance_derivatives_score': 0.0,
            'stablecoin_liquidity_score': 0.0,
            'derivatives_signal': 'NEUTRAL',
        },
    ])
    extra = {
        'binance_derivatives_features': pd.DataFrame([
            {
                'timestamp': '2026-06-01 00:59:00+00:00',
                'binance_derivatives_score': 0.23,
                'derivatives_signal': 'BULLISH',
                'taker_buy_sell_ratio': 1.08,
            },
        ]),
        'stablecoin_liquidity_features': pd.DataFrame([
            {
                'timestamp': '2026-06-01 00:00:00+00:00',
                'stablecoin_liquidity_score': -0.31,
                'stablecoin_total_mcap_7d_change': -0.003,
            },
        ]),
    }
    matrix = build_research_feature_matrix(base, extra, cfg)
    assert matrix['binance_derivatives_score'].iloc[-1] == 0.23
    assert matrix['stablecoin_liquidity_score'].iloc[-1] == -0.31
    assert matrix['derivatives_signal'].iloc[-1] == 'BULLISH'
    assert matrix['optional_extra_data_available'].iloc[-1] is True or bool(matrix['optional_extra_data_available'].iloc[-1]) is True
    assert not any(col.endswith('_x') or col.endswith('_y') for col in matrix.columns)


def test_step1622_backtest_mode_blocks_future_optional_feature_leakage() -> None:
    cfg = load_config('.')
    base = pd.DataFrame([
        {
            'timestamp': '2026-06-01 00:00:00+00:00',
            'close': 100,
            'ma20': 99,
            'ma50': 98,
            # Simulate build_feature_frame's old live-snapshot broadcast. The
            # timestamp-safe builder must strip it before backtest merging.
            'binance_derivatives_score': 0.88,
            'stablecoin_liquidity_score': -0.55,
            'derivatives_signal': 'BULLISH',
        },
        {
            'timestamp': '2026-06-01 01:00:00+00:00',
            'close': 101,
            'ma20': 99,
            'ma50': 98,
            'binance_derivatives_score': 0.88,
            'stablecoin_liquidity_score': -0.55,
            'derivatives_signal': 'BULLISH',
        },
    ])
    extra = {
        'binance_derivatives_features': pd.DataFrame([
            {
                'timestamp': '2026-06-02 00:00:00+00:00',
                'binance_derivatives_score': 0.70,
                'derivatives_signal': 'BULLISH',
            },
        ]),
        'stablecoin_liquidity_features': pd.DataFrame([
            {
                'timestamp': '2026-06-02 00:00:00+00:00',
                'stablecoin_liquidity_score': -0.40,
            },
        ]),
    }
    matrix = build_research_feature_matrix(base, extra, cfg, mode='backtest')
    assert matrix['feature_matrix_mode'].eq('backtest').all()
    assert matrix['binance_derivatives_score'].abs().sum() == 0.0
    assert matrix['stablecoin_liquidity_score'].abs().sum() == 0.0
    assert matrix['optional_extra_data_available'].eq(False).all()
    assert not any(col.endswith('_x') or col.endswith('_y') for col in matrix.columns)


def test_step1622_live_mode_applies_latest_optional_snapshot_only_to_latest_row() -> None:
    cfg = load_config('.')
    base = pd.DataFrame([
        {
            'timestamp': '2026-06-01 00:00:00+00:00',
            'close': 100,
            'ma20': 99,
            'ma50': 98,
            'binance_derivatives_score': 0.88,
            'stablecoin_liquidity_score': -0.55,
        },
        {
            'timestamp': '2026-06-01 01:00:00+00:00',
            'close': 101,
            'ma20': 99,
            'ma50': 98,
            'binance_derivatives_score': 0.88,
            'stablecoin_liquidity_score': -0.55,
        },
    ])
    extra = {
        'binance_derivatives_features': pd.DataFrame([
            {
                'timestamp': '2026-06-02 00:00:00+00:00',
                'binance_derivatives_score': 0.70,
                'derivatives_signal': 'BULLISH',
            },
        ]),
        'stablecoin_liquidity_features': pd.DataFrame([
            {
                'timestamp': '2026-06-02 00:00:00+00:00',
                'stablecoin_liquidity_score': -0.40,
            },
        ]),
    }
    matrix = build_research_feature_matrix(base, extra, cfg, mode='live')
    assert matrix['feature_matrix_mode'].eq('live').all()
    assert matrix['binance_derivatives_score'].iloc[0] == 0.0
    assert matrix['stablecoin_liquidity_score'].iloc[0] == 0.0
    assert matrix['binance_derivatives_score'].iloc[-1] == 0.70
    assert matrix['stablecoin_liquidity_score'].iloc[-1] == -0.40
    assert bool(matrix['optional_extra_data_available'].iloc[0]) is False
    assert bool(matrix['optional_extra_data_available'].iloc[-1]) is True


def test_step1622_backtest_feature_timestamps_never_exceed_price_timestamp() -> None:
    cfg = load_config('.')
    base = pd.DataFrame([
        {'timestamp': '2026-06-01 00:00:00+00:00', 'close': 100, 'ma20': 99, 'ma50': 98},
        {'timestamp': '2026-06-01 01:00:00+00:00', 'close': 101, 'ma20': 99, 'ma50': 98},
        {'timestamp': '2026-06-01 02:00:00+00:00', 'close': 102, 'ma20': 99, 'ma50': 98},
    ])
    extra = {
        'binance_derivatives_features': pd.DataFrame([
            {'timestamp': '2026-06-01 00:30:00+00:00', 'binance_derivatives_score': 0.20},
            {'timestamp': '2026-06-01 03:00:00+00:00', 'binance_derivatives_score': 0.90},
        ]),
        'stablecoin_liquidity_features': pd.DataFrame([
            {'timestamp': '2026-06-01 00:00:00+00:00', 'stablecoin_liquidity_score': 0.10},
        ]),
    }
    matrix = build_research_feature_matrix(base, extra, cfg, mode='backtest')
    price_ts = pd.to_datetime(matrix['timestamp'], utc=True)
    for col in ['extra_derivatives_features_timestamp', 'stablecoin_liquidity_features_timestamp']:
        assert col in matrix.columns
        feature_ts = pd.to_datetime(matrix[col], utc=True, errors='coerce')
        valid = feature_ts.notna()
        assert (feature_ts[valid] <= price_ts[valid]).all()
    assert matrix['binance_derivatives_score'].iloc[-1] == 0.20
