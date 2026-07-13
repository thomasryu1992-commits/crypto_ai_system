from scripts.common import bootstrap
bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.data.raw_data_collector import collect_raw_market_package


if __name__ == '__main__':
    cfg = load_config()
    result = collect_raw_market_package(cfg)
    print('STEP159_DATA_FOUNDATION_OK')
    print('source:', result.get('source'))
    print('rows:', result.get('rows'))
    print('allow_trading:', result.get('data_health', {}).get('allow_trading'))
    print('price_timeframes:', result.get('data_health', {}).get('price_timeframes_loaded'))
    print('raw_files:', len(result.get('raw_files', {})))
    print('normalized_files:', len(result.get('normalized_files', {})))
