from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

from crypto_ai_system.backtest.engine import run_backtest
from crypto_ai_system.backtest.metrics import compute_backtest_summary
from crypto_ai_system.config import load_config
from crypto_ai_system.data.collectors import collect_extended_market_bundle
from crypto_ai_system.execution.safety import assert_no_live_trading, assert_no_testnet_signed_orders
from crypto_ai_system.features.feature_store import build_feature_frame
from crypto_ai_system.strategy.entry_policy import attach_signals
from crypto_ai_system.strategy.research_score import attach_research_scores
from crypto_ai_system.storage.csv_backup import write_df_csv
from crypto_ai_system.storage.latest import write_latest
from crypto_ai_system.storage.paths import ensure_storage_dirs


def main():
    cfg = load_config(ROOT)
    assert_no_live_trading(cfg)
    assert_no_testnet_signed_orders(cfg)
    paths = ensure_storage_dirs(cfg)

    ohlcv, derivatives, mark, index, orderbook, source = collect_extended_market_bundle(cfg)
    features = build_feature_frame(ohlcv, derivatives, cfg, mark=mark, index=index, orderbook=orderbook)
    features = attach_research_scores(features)
    features = attach_signals(features, cfg)

    trades, equity_curve, meta = run_backtest(features, cfg)
    summary = compute_backtest_summary(trades, equity_curve, float(cfg.get('backtest.initial_equity', 10000)))
    summary['source'] = source
    summary['exchange'] = 'extended'
    summary['settlement_asset'] = meta.get('settlement_asset', 'USDC')

    write_df_csv(paths['backtest'] / 'extended_trade_log.csv', trades)
    write_df_csv(paths['backtest'] / 'extended_equity_curve.csv', equity_curve)
    write_latest(paths['backtest'] / 'extended_backtest_summary.json', summary)

    print(json.dumps({
        'ok': True,
        'step': '154E_156E',
        'source': source,
        'summary': summary,
        'trade_log': str(paths['backtest'] / 'extended_trade_log.csv'),
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
