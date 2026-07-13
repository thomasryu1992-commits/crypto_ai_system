from __future__ import annotations

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.data.data_contract import validate_derivatives, validate_ohlcv
from crypto_ai_system.data.data_source_policy import classify_data_source
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline


def test_price_data_source_is_research_only() -> None:
    decision = classify_data_source('price_data_binance_tradingview')
    assert decision.trading_allowed is False
    assert decision.role == 'RESEARCH_BACKTEST_ONLY'
    assert 'NON_LIVE_EXECUTION_DATA_SOURCE:price_data_binance_tradingview' in decision.block_reasons


def test_extended_source_is_execution_eligible() -> None:
    decision = classify_data_source('extended')
    assert decision.trading_allowed is True
    assert decision.role == 'LIVE_EXECUTION_ELIGIBLE'


def test_data_contract_normalizes_ohlcv() -> None:
    df = pd.DataFrame([{ 'timestamp': 1700000000, 'symbol': 'BTC-PERP', 'exchange': 'test', 'exchange_market': 'BTC-USD', 'timeframe': 'PT1H', 'open': '1', 'high': '2', 'low': '0.5', 'close': '1.5', 'volume': '10', 'source': 'unit' }])
    normalized, report = validate_ohlcv(df)
    assert report.ok is True
    assert normalized['close'].iloc[0] == 1.5
    assert '+00:00' in normalized['timestamp'].iloc[0]


def test_data_contract_normalizes_derivatives() -> None:
    df = pd.DataFrame([{ 'timestamp': 1700000000, 'symbol': 'BTC-PERP', 'exchange': 'test', 'exchange_market': 'BTC-USD', 'timeframe': 'PT1H', 'funding_rate': '0.0001', 'open_interest': '100', 'source': 'unit' }])
    normalized, report = validate_derivatives(df)
    assert report.ok is True
    assert normalized['funding_rate'].iloc[0] == 0.0001


def test_pipeline_emits_research_signal() -> None:
    cfg = load_config('.')
    result = run_raw_to_score_pipeline(cfg)
    signal = result['research_signal']
    assert signal['signal_id']
    assert signal['data_source']
    assert signal['entry_side'] in {'LONG', 'SHORT', 'FLAT'}
    assert 'block_reasons' in signal
