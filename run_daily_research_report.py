from scripts.common import bootstrap
bootstrap()

from pathlib import Path
from crypto_ai_system.config import load_config
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline

if __name__ == '__main__':
    cfg = load_config()
    result = run_raw_to_score_pipeline(cfg)
    path = Path(cfg.root) / 'storage' / 'reports' / 'daily' / 'latest_research_report.md'
    print(f'Wrote {path}')
    print(result['report_markdown'])
