from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

from crypto_ai_system.backtest.engine import run_backtest
from crypto_ai_system.backtest.metrics import compute_backtest_summary
from crypto_ai_system.backtest.parameter_sweep import run_parameter_sweep, write_strategy_comparison_report
from crypto_ai_system.config import load_config
from crypto_ai_system.data.collectors import collect_extended_market_bundle
from crypto_ai_system.data.market_snapshot_builder import build_market_snapshot
from crypto_ai_system.execution.safety import assert_no_live_trading, assert_no_testnet_signed_orders
from crypto_ai_system.features.feature_store import build_feature_frame, latest_feature_snapshot
from crypto_ai_system.strategy.entry_policy import attach_signals
from crypto_ai_system.strategy.research_score import attach_research_scores
from crypto_ai_system.storage.csv_backup import write_df_csv
from crypto_ai_system.storage.jsonl import append_jsonl
from crypto_ai_system.storage.latest import write_latest
from crypto_ai_system.storage.paths import ensure_storage_dirs
from crypto_ai_system.storage.spreadsheet_writer import SpreadsheetWriter


def main():
    cfg = load_config(ROOT)
    assert_no_live_trading(cfg)
    assert_no_testnet_signed_orders(cfg)
    paths = ensure_storage_dirs(cfg)

    ohlcv, derivatives, mark, index, orderbook, source = collect_extended_market_bundle(cfg)
    snapshot = build_market_snapshot(ohlcv, derivatives, source=source, mark=mark, index=index, orderbook=orderbook).to_dict()
    write_latest(paths['latest'] / 'extended_market_snapshot.json', snapshot)
    write_latest(paths['latest'] / 'market_snapshot.json', snapshot)
    write_df_csv(paths['backup'] / 'extended_ohlcv_history.csv', ohlcv)
    write_df_csv(paths['backup'] / 'extended_derivatives_history.csv', derivatives)
    write_df_csv(paths['backup'] / 'extended_mark_price_history.csv', mark)
    write_df_csv(paths['backup'] / 'extended_index_price_history.csv', index)
    SpreadsheetWriter(paths['backup'], paths['queue'] / 'spreadsheet_retry_queue.jsonl').write_row('extended_market_snapshot', snapshot)

    features = build_feature_frame(ohlcv, derivatives, cfg, mark=mark, index=index, orderbook=orderbook)
    features = attach_research_scores(features)
    features = attach_signals(features, cfg)
    feature_snapshot = latest_feature_snapshot(features)
    feature_snapshot['source'] = source
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

    append_jsonl(paths['logs'] / 'event_log.jsonl', {
        'type': 'step157e_validation_complete',
        'source': source,
        'market': snapshot.get('exchange_market'),
        'trades': len(trades),
        'sweep_candidates': len(sweep),
    })

    result = {
        'ok': True,
        'package': 'crypto_ai_system_step157e',
        'source': source,
        'market': snapshot.get('exchange_market'),
        'canonical_symbol': snapshot.get('symbol'),
        'settlement_asset': snapshot.get('settlement_asset'),
        'step151e_market_snapshot': str(paths['latest'] / 'extended_market_snapshot.json'),
        'step152e_feature_snapshot': str(paths['latest'] / 'extended_feature_snapshot.json'),
        'step154e_backtest_summary': summary,
        'step157e_best_candidate': candidates[0] if candidates else None,
        'safety': {
            'live_trading_enabled': False,
            'testnet_signed_order_enabled': False,
        },
        'preserved': {
            'spreadsheet_first_writer': True,
            'coinalyze_enrichment_seam': True,
            'binance_collector_removed_from_main_flow': True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
