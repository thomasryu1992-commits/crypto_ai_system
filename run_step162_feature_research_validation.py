from scripts.common import bootstrap
bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline


def _disable_network_collectors_for_local_validation(cfg):
    import os
    run_network = str(os.getenv('RUN_NETWORK_TESTS', 'false')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    if run_network:
        return cfg, 'enabled'
    additional = cfg.settings.setdefault('additional_data', {})
    additional.setdefault('binance_futures', {})['enabled'] = False
    additional.setdefault('coinmetrics', {})['enabled'] = False
    additional.setdefault('defillama', {})['enabled'] = False
    # Keep Farside CSV enabled because it is local/manual input.
    additional.setdefault('farside', {})['enabled'] = True
    return cfg, 'disabled_for_local_validation'


if __name__ == '__main__':
    cfg = load_config()
    cfg, network_collectors = _disable_network_collectors_for_local_validation(cfg)
    result = run_raw_to_score_pipeline(cfg)
    signal = result.get('research_signal', {})
    matrix = result.get('research_feature_matrix', {})
    print('network_collectors:', network_collectors)
    print('STEP162_FEATURE_RESEARCH_VALIDATION_OK')
    print('signal_version:', signal.get('version'))
    print('entry_side:', signal.get('entry_side'))
    print('trade_permission:', signal.get('trade_permission'))
    print('feature_matrix_rows:', matrix.get('rows'))
    print('feature_store_files:', sorted((result.get('feature_store_files') or {}).keys()))
