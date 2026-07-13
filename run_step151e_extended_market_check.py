from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

from crypto_ai_system.config import load_config
from crypto_ai_system.data.collectors import collect_extended_market_bundle
from crypto_ai_system.data.market_snapshot_builder import build_market_snapshot
from crypto_ai_system.execution.safety import assert_no_live_trading, assert_no_testnet_signed_orders
from crypto_ai_system.storage.csv_backup import write_df_csv
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
    write_df_csv(paths['backup'] / 'extended_ohlcv_history.csv', ohlcv)
    write_df_csv(paths['backup'] / 'extended_derivatives_history.csv', derivatives)
    write_df_csv(paths['backup'] / 'extended_mark_price_history.csv', mark)
    write_df_csv(paths['backup'] / 'extended_index_price_history.csv', index)
    SpreadsheetWriter(paths['backup'], paths['queue'] / 'spreadsheet_retry_queue.jsonl').write_row('extended_market_snapshot', snapshot)

    print(json.dumps({
        'ok': True,
        'step': '151E',
        'source': source,
        'snapshot_path': str(paths['latest'] / 'extended_market_snapshot.json'),
        'ohlcv_rows': len(ohlcv),
        'derivatives_rows': len(derivatives),
        'spread_bps': snapshot.get('spread_bps'),
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
