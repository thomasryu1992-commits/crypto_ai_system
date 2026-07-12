from __future__ import annotations

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_bot import ResearchBot
from crypto_ai_system.trading.trading_bot import TradingBot


def _price_frame(rows: int = 120) -> pd.DataFrame:
    ts = pd.date_range('2026-06-01 00:00:00+00:00', periods=rows, freq='h')
    close = [100_000 + i * 80 + (300 if i % 6 in {1, 2, 3} else -300) for i in range(rows)]
    return pd.DataFrame({
        'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S+00:00'),
        'symbol': 'BTC-PERP',
        'timeframe': 'PT1H',
        'exchange': 'extended',
        'exchange_market': 'BTC-USD',
        'open': [c - 30 for c in close],
        'high': [c + 120 for c in close],
        'low': [c - 150 for c in close],
        'close': close,
        'volume': [1000 + i for i in range(rows)],
    })


def _derivatives_frame(rows: int = 120) -> pd.DataFrame:
    ts = pd.date_range('2026-06-01 00:00:00+00:00', periods=rows, freq='h')
    open_interest = [1_000_000 + i * 2000 for i in range(rows)]
    return pd.DataFrame({
        'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S+00:00'),
        'funding_rate': [0.0001] * rows,
        'open_interest': open_interest,
        'open_interest_base': [10_000 + i * 10 for i in range(rows)],
        'oi_change_pct': [0.01] * rows,
        'long_liquidation': [0.0] * rows,
        'short_liquidation': [0.0] * rows,
    })




def _step258_cfg():
    cfg = load_config('.')
    cfg.settings.setdefault('entry_policy', {})['bullish_threshold'] = 0.30
    cfg.settings.setdefault('entry_policy', {})['bearish_threshold'] = -0.30
    cfg.settings.setdefault('price_data', {})['include_multi_timeframe_context'] = False
    return cfg

def _supportive_extra_frames() -> dict[str, pd.DataFrame]:
    ts = '2026-06-05 23:00:00+00:00'
    return {
        'binance_derivatives_features': pd.DataFrame([{
            'timestamp': ts,
            'binance_derivatives_score': 0.45,
            'derivatives_signal': 'BULLISH',
            'taker_buy_sell_ratio': 1.08,
            'top_trader_position_long_short_ratio': 1.12,
        }]),
        'exchange_flow_features': pd.DataFrame([{
            'timestamp': ts,
            'exchange_flow_score': 0.42,
            'btc_exchange_netflow': -1200.0,
            'exchange_netflow_zscore_30d': -1.4,
            'netflow_signal': 'ACCUMULATION',
        }]),
        'etf_flow_features': pd.DataFrame([{
            'timestamp': ts,
            'etf_flow_score': 0.50,
            'total_flow_usd_m': 280.0,
            'etf_flow_5d_sum': 900.0,
            'etf_signal': 'INFLOW',
        }]),
        'stablecoin_liquidity_features': pd.DataFrame([{
            'timestamp': ts,
            'stablecoin_liquidity_score': 0.35,
            'stablecoin_total_mcap_7d_change': 0.006,
        }]),
    }


def test_step258_extra_feature_store_feeds_researchsignal_v2_and_trading_bot_gate() -> None:
    cfg = _step258_cfg()
    bot = ResearchBot(cfg)
    result = bot.analyze(
        _price_frame(),
        _derivatives_frame(),
        orderbook={
            'bid_price': 109_490,
            'ask_price': 109_510,
            'spread_bps': 2,
            'additional_feature_frames': _supportive_extra_frames(),
        },
        source='extended',
    )

    signal = result.research_signal
    matrix = bot.latest_feature_matrix_live
    assert signal['version'] == 'research_signal_v2_step259_weight_calibration_permission_distribution'
    assert matrix['feature_matrix_version'].iloc[-1] == 'step259_weight_calibration_permission_distribution_matrix'
    assert bool(matrix['optional_extra_data_available'].iloc[-1]) is True
    assert signal['score_components']['exchange_flow'] is not None
    assert signal['features']['etf_flow_5d'] == 900.0
    assert signal['trade_permission']['allow_new_position'] is True
    assert signal['entry_side'] == 'LONG'

    trade_plan = TradingBot(cfg).build_trade_plan(signal)
    assert trade_plan['status'] == 'TRADE_CANDIDATE'
    assert trade_plan['trade_plan']['permission_gate_applied'] is True
    assert trade_plan['trade_plan']['research_signal_id'] == signal['signal_id']


def test_step258_missing_optional_data_defaults_to_neutral_without_blocking_feature_store() -> None:
    cfg = _step258_cfg()
    bot = ResearchBot(cfg)
    result = bot.analyze(
        _price_frame(),
        _derivatives_frame(),
        orderbook={'bid_price': 109_490, 'ask_price': 109_510, 'spread_bps': 2},
        source='extended',
    )
    matrix = bot.latest_feature_matrix_live
    assert bool(matrix['optional_extra_data_available'].iloc[-1]) is False
    for col in ['binance_derivatives_score', 'exchange_flow_score', 'etf_flow_score', 'stablecoin_liquidity_score']:
        assert float(matrix[col].iloc[-1]) == 0.0
    signal = result.research_signal
    assert signal['version'] == 'research_signal_v2_step259_weight_calibration_permission_distribution'
    assert signal['features']['exchange_flow_score'] == 0.0
    assert signal['features']['stablecoin_liquidity_score'] == 0.0


def test_step258_risk_off_extra_data_blocks_trade_permission_before_plan() -> None:
    cfg = _step258_cfg()
    cfg.settings.setdefault('research', {})['score_weights'] = {
        'structure': 0.70,
        'momentum': 0.10,
        'derivatives': 0.20,
        'exchange_flow': 0.00,
        'etf_flow': 0.00,
        'stablecoin_liquidity': 0.00,
        'risk': 0.00,
        'onchain': 0.00,
    }
    bot = ResearchBot(cfg)
    risky = _supportive_extra_frames()
    risky['exchange_flow_features'].loc[0, 'exchange_flow_score'] = -0.80
    risky['exchange_flow_features'].loc[0, 'netflow_signal'] = 'SELL_PRESSURE'
    risky['etf_flow_features'].loc[0, 'etf_flow_score'] = -0.90
    risky['etf_flow_features'].loc[0, 'etf_signal'] = 'OUTFLOW'
    risky['stablecoin_liquidity_features'].loc[0, 'stablecoin_liquidity_score'] = -0.90

    result = bot.analyze(
        _price_frame(),
        _derivatives_frame(),
        orderbook={
            'bid_price': 109_490,
            'ask_price': 109_510,
            'spread_bps': 2,
            'additional_feature_frames': risky,
        },
        source='extended',
    )
    signal = result.research_signal
    assert signal['entry_side'] == 'FLAT'
    assert signal['entry_allowed'] is False
    assert signal['trade_permission']['risk_level'] == 'blocked'
    assert 'EXCHANGE_FLOW_SELL_PRESSURE_BLOCK' in signal['trade_permission']['block_reasons']
    assert 'ETF_OUTFLOW_BLOCK' in signal['trade_permission']['block_reasons']
    assert 'STABLECOIN_LIQUIDITY_CONTRACTION_BLOCK' in signal['trade_permission']['block_reasons']

    trade_plan = TradingBot(cfg).build_trade_plan(signal)
    assert trade_plan['status'] == 'NO_TRADE'
    assert trade_plan['trade_plan'] is None
    assert trade_plan['signal']['permission_gate_applied'] is True
