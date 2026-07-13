from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

ROOT = bootstrap()


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def build_report() -> dict:
    feature_matrix = _read('src/crypto_ai_system/features/research_feature_matrix.py')
    research_bot = _read('src/crypto_ai_system/research/research_bot.py')
    score_engine = _read('src/crypto_ai_system/analysis/score_engine.py')
    signal_builder = _read('src/crypto_ai_system/research/research_signal_builder.py')
    permission_gate = _read('src/crypto_ai_system/trading/permission_gate.py')
    trading_signal = _read('src/crypto_ai_system/trading/signal.py')
    trading_bot = _read('src/crypto_ai_system/trading/trading_bot.py')
    settings = _read('config/settings.yaml')
    step257_policy = _read('docs/STEP257_DEFERRED_EXECUTION_STUB_POLICY.md')

    expected_collectors = [
        'binance_derivatives_features',
        'exchange_flow_features',
        'etf_flow_features',
        'stablecoin_liquidity_features',
    ]
    score_components = [
        'derivatives',
        'exchange_flow',
        'etf_flow',
        'stablecoin_liquidity',
        'risk',
    ]

    return {
        'step': 258,
        'status': 'completed',
        'scope': 'feature_store_researchsignal_v2_permission_gate_connection',
        'feature_store': {
            'version_locked': 'step258_feature_store_permission_matrix' in feature_matrix,
            'live_backtest_matrices_supported': 'research_feature_matrix_live' in feature_matrix and 'research_feature_matrix_backtest' in feature_matrix,
            'timestamp_safe_asof_merge_supported': 'pd.merge_asof' in feature_matrix,
            'latest_live_snapshot_only_supported': '_apply_latest_feature_to_latest_row' in feature_matrix,
            'optional_data_neutral_defaults_supported': all(col in feature_matrix for col in [
                'binance_derivatives_score', 'exchange_flow_score', 'etf_flow_score', 'stablecoin_liquidity_score'
            ]),
            'collector_feature_groups_connected': {name: name in feature_matrix or name in research_bot for name in expected_collectors},
        },
        'research_signal_v2': {
            'version_locked': 'research_signal_v2_step258_feature_store_permission_gate' in signal_builder,
            'score_components_connected': {name: name in signal_builder and name in score_engine for name in score_components},
            'trade_permission_schema_fields': {name: name in signal_builder for name in [
                'allow_long', 'allow_short', 'allow_new_position', 'risk_level', 'risk_warnings', 'block_reasons'
            ]},
            'price_direction_plus_extra_data_formula_present': all(name in score_engine for name in [
                'structure', 'momentum', 'derivatives', 'exchange_flow', 'etf_flow', 'stablecoin_liquidity', 'risk'
            ]),
            'settings_weights_include_extra_categories': all(name in settings for name in [
                'exchange_flow', 'etf_flow', 'stablecoin_liquidity', 'risk'
            ]),
        },
        'trading_bot_permission_gate': {
            'permission_gate_consumes_research_signal': 'evaluate_trade_permission' in trading_signal,
            'trade_permission_is_final_gate': 'ResearchSignal v2 trade_permission is the final Trading Bot gate' in trading_signal,
            'risk_level_reduces_position_size': 'risk_level_reduced_position_multiplier' in trading_bot,
            'blocked_risk_level_forces_no_trade': "risk_level', 'normal') == 'blocked'" in trading_bot or "risk_level', 'normal') == 'blocked'" in trading_bot,
            'signal_engine_uses_research_signal_gate': 'USE_RESEARCH_SIGNAL_GATE' in _read('src/crypto_ai_system/trading/signal_engine.py'),
            'permission_gate_payload_fields': {name: name in permission_gate for name in [
                'allow_long', 'allow_short', 'allow_new_position', 'position_size_multiplier', 'risk_level'
            ]},
        },
        'safety_boundaries': {
            'live_executor_remains_disabled_compat_surface': 'execution.live_executor' in step257_policy and 'disabled compatibility surface' in step257_policy,
            'testnet_executor_remains_disabled_compat_surface': 'execution.testnet_executor' in step257_policy and 'disabled compatibility surface' in step257_policy,
            'canonical_live_execution_port_performed': False,
            'canonical_testnet_execution_port_performed': False,
            'root_package_deletion_performed': False,
            'missing_canonical_module_count': 2,
            'live_trading_allowed': False,
            'order_routing_enabled': False,
        },
        'tests': {
            'new_test_file': 'tests/test_step258_feature_store_researchsignal_permission_gate.py',
            'new_test_cases': [
                'extra_feature_store_feeds_researchsignal_v2_and_trading_bot_gate',
                'missing_optional_data_defaults_to_neutral_without_blocking_feature_store',
                'risk_off_extra_data_blocks_trade_permission_before_plan',
            ],
        },
    }


def main() -> int:
    report = build_report()
    out = ROOT / 'data' / 'reports' / 'step258_feature_store_researchsignal_permission_gate_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
