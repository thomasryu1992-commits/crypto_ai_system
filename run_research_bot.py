from scripts.common import bootstrap
bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline

if __name__ == '__main__':
    cfg = load_config()
    result = run_raw_to_score_pipeline(cfg)
    print(result['report_markdown'])
