from __future__ import annotations

from crypto_ai_system.config import load_config
from crypto_ai_system.trading.permission_gate import evaluate_trade_permission, trading_signal_payload_from_research_signal
from crypto_ai_system.trading.trading_bot import TradingBot
from crypto_ai_system.trading.permission_gate import signal_payload_from_research_signal


def _base_research_signal(**overrides):
    payload = {
        'signal_id': 'sig_step163_unit',
        'version': 'research_signal_v2_step258_feature_store_permission_gate',
        'symbol': 'BTC-PERP',
        'entry_side': 'LONG',
        'entry_allowed': True,
        'entry_confidence': 0.72,
        'close': 100000,
        'atr': 500,
        'trade_permission': {
            'allow_long': True,
            'allow_short': False,
            'allow_new_position': True,
            'risk_level': 'normal',
            'risk_warnings': [],
            'block_reasons': [],
        },
    }
    payload.update(overrides)
    return payload


def test_step163_permission_gate_allows_normal_long() -> None:
    decision = evaluate_trade_permission(_base_research_signal())
    assert decision.entry_allowed is True
    assert decision.side == 'LONG'
    assert decision.risk_level == 'normal'
    assert decision.position_size_multiplier == 1.0


def test_step163_permission_gate_blocks_risk_level_blocked() -> None:
    signal = _base_research_signal(
        trade_permission={
            'allow_long': True,
            'allow_short': False,
            'allow_new_position': False,
            'risk_level': 'blocked',
            'block_reasons': ['STABLECOIN_LIQUIDITY_CONTRACTION_BLOCK'],
        }
    )
    payload = trading_signal_payload_from_research_signal(signal)
    assert payload['signal'] == 'NONE'
    assert payload['allow_new_position'] is False
    assert payload['risk_level'] == 'blocked'
    assert payload['position_size_multiplier'] == 0.0
    assert 'STABLECOIN_LIQUIDITY_CONTRACTION_BLOCK' in payload['block_reasons']


def test_step163_permission_gate_reduced_risk_reduces_trade_plan_size() -> None:
    cfg = load_config('.')
    normal = _base_research_signal(trade_permission={
        'allow_long': True,
        'allow_short': False,
        'allow_new_position': True,
        'risk_level': 'normal',
    })
    reduced = _base_research_signal(trade_permission={
        'allow_long': True,
        'allow_short': False,
        'allow_new_position': True,
        'risk_level': 'reduced',
        'risk_warnings': ['FUNDING_ELEVATED_REDUCE_SIZE'],
    })
    normal_plan = TradingBot(cfg).build_trade_plan(normal)['trade_plan']
    reduced_plan = TradingBot(cfg).build_trade_plan(reduced)['trade_plan']
    assert normal_plan is not None
    assert reduced_plan is not None
    assert reduced_plan['position_size_multiplier'] == 0.5
    assert reduced_plan['risk_amount_usdc'] < normal_plan['risk_amount_usdc']


def test_step163_legacy_wrapper_outputs_signal_payload() -> None:
    payload = signal_payload_from_research_signal(_base_research_signal())
    assert payload['permission_gate_applied'] is True
    assert payload['signal'] == 'LONG'
    assert payload['allow_new_position'] is True
    assert payload['risk_level'] == 'normal'
