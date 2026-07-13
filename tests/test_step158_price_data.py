from __future__ import annotations

from crypto_ai_system.config import load_config
from crypto_ai_system.data.price_data_loader import build_multi_timeframe_context, load_price_history_bundle, select_primary_ohlcv_from_price_bundle
from crypto_ai_system.trading.trading_bot import TradingBot


def test_embedded_btc_price_data_all_timeframes_loaded() -> None:
    cfg = load_config('.')
    bundle = load_price_history_bundle(cfg)
    assert set(bundle.keys()) == {'15m', '1h', '4h', '1d', '3d', '1w', '1m'}
    assert not select_primary_ohlcv_from_price_bundle(cfg, bundle).empty


def test_multi_timeframe_context_available() -> None:
    cfg = load_config('.')
    ctx = build_multi_timeframe_context(cfg)
    assert ctx['available'] is True
    assert 'alignment_score' in ctx
    assert set(ctx['timeframes'].keys()) == {'15m', '1h', '4h', '1d', '3d', '1w', '1m'}


def test_non_live_price_data_blocks_trade_signal() -> None:
    cfg = load_config('.')
    snapshot = {
        'canonical_symbol': 'BTC-PERP',
        'close': 60000,
        'atr': 500,
        'score_total_score': 0.9,
        'market_condition': 'BULLISH_TREND_OPPORTUNITY',
        'spread_bps': 4,
        'data_source': 'price_data_binance_tradingview',
        'trading_allowed_by_data_source': False,
        'data_block_reasons': ['NON_LIVE_EXECUTION_DATA_SOURCE:price_data_binance_tradingview'],
    }
    result = TradingBot(cfg).build_trade_plan(snapshot)
    assert result['status'] == 'NO_TRADE'
    assert result['trade_plan'] is None
