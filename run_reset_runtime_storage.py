from scripts.common import bootstrap
bootstrap()

import shutil
from pathlib import Path
from crypto_ai_system.config import load_config

if __name__ == '__main__':
    cfg = load_config()
    for rel in ['storage/latest', 'storage/backtest', 'storage/logs', 'storage/queue', 'storage/paper', 'storage/research', 'storage/trading']:
        p = cfg.root / rel
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)
    print('Runtime storage reset complete. Raw and spreadsheet backup folders were preserved.')
