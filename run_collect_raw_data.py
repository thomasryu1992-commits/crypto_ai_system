from scripts.common import bootstrap
bootstrap()

import json
from crypto_ai_system.config import load_config
from crypto_ai_system.data.raw_data_collector import collect_raw_market_package

if __name__ == '__main__':
    cfg = load_config()
    result = collect_raw_market_package(cfg)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
