from scripts.common import bootstrap
bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.data.additional_data_collector import collect_additional_data_package
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
    package = collect_additional_data_package(cfg, persist=True)
    result = run_raw_to_score_pipeline(cfg)
    signal = result.get('research_signal', {})
    print('network_collectors:', network_collectors)
    print('STEP161_EXTRA_DATA_VALIDATION_OK')
    print('raw_frames:', package.to_summary().get('raw_frames'))
    print('feature_frames:', package.to_summary().get('feature_frames'))
    print('signal_version:', signal.get('version'))
    print('score_components:', signal.get('score_components'))
    print('features:', signal.get('features'))
