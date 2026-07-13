from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

from crypto_ai_system.config import load_config
from crypto_ai_system.data.collectors import collect_extended_market_bundle
from crypto_ai_system.execution.safety import assert_no_live_trading, assert_no_testnet_signed_orders
from crypto_ai_system.features.feature_store import build_feature_frame, latest_feature_snapshot
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
    snapshot = latest_feature_snapshot(features)
    snapshot['source'] = source

    write_latest(paths['latest'] / 'extended_feature_snapshot.json', snapshot)
    write_df_csv(paths['backup'] / 'extended_feature_history.csv', features)

    print(json.dumps({
        'ok': True,
        'step': '152E_153E',
        'source': source,
        'rows': len(features),
        'latest_regime': snapshot.get('market_regime'),
        'latest_signal': snapshot.get('signal'),
        'snapshot_path': str(paths['latest'] / 'extended_feature_snapshot.json'),
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
