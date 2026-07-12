from __future__ import annotations

import pandas as pd

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_calibration import (
    STEP259_CALIBRATION_VERSION,
    compare_weight_profiles,
    normalize_score_weights,
    resolve_weight_profiles,
)
from crypto_ai_system.notifier.telegram import build_telegram_message
from notify.telegram_summary_builder import build_daily_telegram_message, extract_extra_data_summary
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix, build_report


def test_step259_weight_profiles_are_normalized_and_resolved() -> None:
    cfg = load_config('.')
    profiles = resolve_weight_profiles(cfg)
    assert {'baseline_step258', 'price_structure_dominant', 'flow_confirmed', 'liquidity_risk_guarded'} <= set(profiles)
    for weights in profiles.values():
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        assert all(value >= 0 for value in weights.values())

    normalized = normalize_score_weights({'structure': 2, 'momentum': 1, 'derivatives': 1})
    assert abs(sum(normalized.values()) - 1.0) < 1e-6
    assert normalized['structure'] > normalized['momentum']


def test_step259_compare_weight_profiles_reports_permission_distribution() -> None:
    cfg = load_config('.')
    matrix = _synthetic_calibration_matrix(rows=36)
    report = compare_weight_profiles(matrix, cfg)

    assert report['version'] == STEP259_CALIBRATION_VERSION
    assert report['profiles_compared'] >= 4
    assert report['rows_evaluated'] == 36
    for item in report['results']:
        assert item['status'] == 'OK'
        assert item['rows'] == 36
        assert {'normal', 'reduced', 'blocked'} <= set(item['permission_distribution'])
        assert {'LONG', 'SHORT', 'FLAT'} <= set(item['side_distribution'])
        assert 0.0 <= item['entry_allowed_ratio'] <= 1.0
        assert 0.0 <= item['blocked_ratio'] <= 1.0

    baseline = next(x for x in report['results'] if x['profile_name'] == 'baseline_step258')
    assert baseline['permission_distribution']['blocked'] > 0
    assert 'ETF_OUTFLOW_BLOCK' in baseline['block_reason_counts']


def test_step259_report_builder_uses_synthetic_matrix_without_live_side_effects(tmp_path) -> None:
    report = build_report(tmp_path if False else __import__('pathlib').Path('.').resolve(), max_rows=24)
    assert report['step'] == 259
    assert report['status'] == 'completed'
    assert report['comparison']['profiles_compared'] >= 4
    assert report['comparison']['rows_evaluated'] <= 24
    assert report['safety_boundaries']['missing_canonical_module_count'] == 2
    assert report['safety_boundaries']['external_order_submission_performed'] is False
    assert report['telegram_extra_data_summary_connected'] is True


def _research_cycle_with_extra_data() -> dict:
    return {
        'research_signal': {
            'features': {
                'binance_derivatives_score': 0.45,
                'exchange_flow_score': 0.42,
                'etf_flow_score': 0.50,
                'stablecoin_liquidity_score': 0.35,
                'exchange_netflow_zscore_30d': -1.4,
                'etf_flow_5d': 900.0,
                'stablecoin_supply_change_7d': 0.006,
            },
            'score_components': {
                'derivatives': 0.38,
                'exchange_flow': 0.42,
                'etf_flow': 0.50,
                'stablecoin_liquidity': 0.35,
                'risk': -0.10,
            },
        },
        'report_date': '2026-06-30',
        'current_price': 109500,
        'market_bias': 'BULLISH',
        'research_score': 65,
        'summary': {'base_case': 'Long only if structure confirms', 'key_reason': 'Flow support', 'risk_note': 'Watch funding'},
    }


def test_step259_telegram_daily_summary_includes_extra_data_section() -> None:
    extra = extract_extra_data_summary(_research_cycle_with_extra_data())
    assert extra['exchange_flow_score'] == 0.42
    assert extra['etf_flow_5d'] == 900.0

    message = build_daily_telegram_message(
        daily_report={},
        research_cycle_result=_research_cycle_with_extra_data(),
        paper_report={'signal': {'side': 'LONG', 'confidence': 0.7}, 'position_opened': False, 'mode': 'paper'},
        scheduler_health={},
        markdown_report_result={},
        signal_quality_report={},
        signal_calibration_advice={},
        trading_cycle_result={'permission_gate': {'permission_gate_applied': True, 'allow_long': True, 'allow_short': False, 'allow_new_position': True, 'risk_level': 'normal'}},
    )
    assert '[Extra Data Summary]' in message
    assert 'Exchange Flow Score: +0.42' in message
    assert 'Stablecoin Supply 7D: +0.60%' in message


def test_step259_src_notifier_telegram_includes_extra_data_summary() -> None:
    msg = build_telegram_message(
        'Daily summary',
        trade_decision={
            'research_signal': _research_cycle_with_extra_data()['research_signal'],
            'signal': {'allow_new_position': True, 'risk_level': 'normal'},
        },
    )
    assert 'Extra Data Summary:' in msg
    assert 'Derivatives Score: +0.45' in msg
    assert 'ETF Flow 5D: 900.0' in msg
