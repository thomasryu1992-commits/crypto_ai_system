from scripts.common import bootstrap
bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.data.additional_data_collector import collect_and_persist_additional_data


if __name__ == '__main__':
    cfg = load_config()
    result = collect_and_persist_additional_data(cfg)
    print('ADDITIONAL_DATA_COLLECTOR_OK')
    print('raw_frames:', result.get('raw_frames'))
    print('feature_frames:', result.get('feature_frames'))
    print('snapshot_keys:', len(result.get('feature_snapshot_keys', [])))
