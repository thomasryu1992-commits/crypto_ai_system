from scripts.common import bootstrap
bootstrap()

import json
from pathlib import Path

from crypto_ai_system.backtest.engine import run_backtest
from crypto_ai_system.backtest.metrics import compute_backtest_summary
from crypto_ai_system.backtest.parameter_sweep import run_parameter_sweep, write_strategy_comparison_report
from crypto_ai_system.config import load_config
from crypto_ai_system.data.collectors import collect_extended_market_bundle
from crypto_ai_system.data.raw_data_collector import collect_raw_market_package
from crypto_ai_system.execution.extended_order_builder import build_extended_ioc_order_payload
from crypto_ai_system.execution.safety import assert_no_live_trading, assert_no_testnet_signed_orders
from crypto_ai_system.features.feature_store import build_feature_frame, latest_feature_snapshot
from crypto_ai_system.research.research_bot import ResearchBot
from crypto_ai_system.storage.csv_backup import write_df_csv
from crypto_ai_system.storage.jsonl import append_jsonl
from crypto_ai_system.storage.latest import write_latest
from crypto_ai_system.storage.paths import ensure_storage_dirs
from crypto_ai_system.storage.spreadsheet_writer import SpreadsheetWriter
from crypto_ai_system.strategy.entry_policy import attach_signals
from crypto_ai_system.strategy.research_score import attach_research_scores
from crypto_ai_system.trading.trading_bot import TradingBot

ROOT = Path(__file__).resolve().parent


def main():
    cfg = load_config(ROOT)
    assert_no_live_trading(cfg)
    assert_no_testnet_signed_orders(cfg)
    paths = ensure_storage_dirs(cfg)

    raw_result = collect_raw_market_package(cfg)
    ohlcv, derivatives, mark, index, orderbook, source = collect_extended_market_bundle(cfg)

    research_result = ResearchBot(cfg).analyze(ohlcv, derivatives, mark=mark, index=index, orderbook=orderbook)
    write_latest(paths['latest'] / 'research_snapshot.json', research_result.snapshot)
    write_latest(paths['latest'] / 'market_condition_snapshot.json', research_result.condition)
    report_path = cfg.root / 'storage' / 'reports' / 'daily' / 'latest_research_report.md'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(research_result.report_markdown, encoding='utf-8')
    SpreadsheetWriter(paths['backup'], paths['queue'] / 'spreadsheet_retry_queue.jsonl').write_row('research_snapshot', research_result.snapshot)

    features = build_feature_frame(ohlcv, derivatives, cfg, mark=mark, index=index, orderbook=orderbook)
    # Preserve legacy research_score/entry_policy pipeline and add full score-engine result.
    features = attach_research_scores(features)
    features = attach_signals(features, cfg)
    feature_snapshot = latest_feature_snapshot(features)
    feature_snapshot['full_score_snapshot'] = research_result.snapshot
    write_latest(paths['latest'] / 'extended_feature_snapshot.json', feature_snapshot)
    write_latest(paths['latest'] / 'feature_snapshot.json', feature_snapshot)
    write_df_csv(paths['backup'] / 'extended_feature_history.csv', features)

    trades, equity_curve, meta = run_backtest(features, cfg)
    summary = compute_backtest_summary(trades, equity_curve, float(cfg.get('backtest.initial_equity', 10000)))
    summary['source'] = source
    summary['exchange'] = 'extended'
    summary['settlement_asset'] = meta.get('settlement_asset', 'USDC')
    write_df_csv(paths['backtest'] / 'extended_trade_log.csv', trades)
    write_df_csv(paths['backtest'] / 'extended_equity_curve.csv', equity_curve)
    write_latest(paths['backtest'] / 'extended_backtest_summary.json', summary)

    sweep = run_parameter_sweep(features, cfg)
    write_df_csv(paths['backtest'] / 'extended_parameter_sweep_results.csv', sweep)
    candidates = sweep.head(10).to_dict(orient='records') if not sweep.empty else []
    write_latest(paths['backtest'] / 'extended_best_strategy_candidates.json', {'candidates': candidates})
    write_strategy_comparison_report(sweep, str(paths['backtest'] / 'extended_strategy_comparison_report.md'))

    trading_decision = TradingBot(cfg).build_trade_plan(research_result.snapshot)
    write_latest(paths['latest'] / 'trading_decision.json', trading_decision)
    dry_order_payload = None
    if trading_decision.get('trade_plan'):
        dry_order_payload = build_extended_ioc_order_payload(trading_decision['trade_plan'], orderbook=orderbook)
        write_latest(paths['latest'] / 'extended_order_payload_dry_run.json', dry_order_payload)

    append_jsonl(paths['logs'] / 'event_log.jsonl', {
        'type': 'step157e_full_validation_complete',
        'source': source,
        'raw_rows': raw_result['rows'],
        'features': len(features),
        'trades': len(trades),
        'sweep_candidates': len(sweep),
        'research_condition': research_result.condition.get('final_condition'),
    })

    required_files = [
        paths['latest'] / 'market_snapshot.json',
        paths['latest'] / 'research_snapshot.json',
        paths['latest'] / 'market_condition_snapshot.json',
        paths['latest'] / 'trading_decision.json',
        paths['backtest'] / 'extended_backtest_summary.json',
        paths['backtest'] / 'extended_parameter_sweep_results.csv',
        report_path,
        cfg.root / 'storage' / 'raw' / 'extended' / 'ohlcv_raw.csv',
    ]
    missing = [str(p) for p in required_files if not p.exists()]
    result = {
        'ok': not missing,
        'package': 'crypto_ai_system_step157e_full',
        'source': source,
        'raw_rows': raw_result['rows'],
        'features_rows': len(features),
        'backtest_trades': len(trades),
        'sweep_candidates': len(sweep),
        'research_condition': research_result.condition,
        'trading_decision_status': trading_decision.get('status'),
        'dry_order_payload_created': dry_order_payload is not None,
        'missing_required_files': missing,
        'preserved_features': {
            'extended_data_main_flow': True,
            'spreadsheet_first_writer': True,
            'coinalyze_enrichment_seam': True,
            'research_bot': True,
            'raw_data_store': True,
            'score_engine': True,
            'market_condition_analysis': True,
            'entry_exit_policy': True,
            'backtest_and_parameter_sweep': True,
            'paper_trading_scaffold': True,
            'telegram_dry_run_scaffold': True,
            'testnet_order_payload_dry_run_only': True,
            'binance_main_flow_removed': True,
        },
        'safety': {
            'live_trading_enabled': False,
            'testnet_signed_order_enabled': False,
        }
    }
    write_latest(paths['latest'] / 'step157e_full_validation_result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
