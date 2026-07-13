from scripts.common import bootstrap
bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline


if __name__ == '__main__':
    cfg = load_config()
    result = run_raw_to_score_pipeline(cfg)
    signal = result.get('research_signal', {})
    print('STEP160_RESEARCH_SIGNAL_OK')
    print('signal_id:', signal.get('signal_id'))
    print('source:', signal.get('data_source'))
    print('entry_side:', signal.get('entry_side'))
    print('entry_allowed:', signal.get('entry_allowed'))
    print('block_reasons:', signal.get('block_reasons'))
