from scripts.common import bootstrap
bootstrap()

import json
from crypto_ai_system.config import load_config
from crypto_ai_system.research.raw_score_pipeline import run_raw_to_score_pipeline
from crypto_ai_system.trading.trading_bot import TradingBot
from crypto_ai_system.notifier.summary_builder import build_daily_notification
from crypto_ai_system.notifier.telegram import send_telegram_message
from crypto_ai_system.storage.latest import write_latest
from crypto_ai_system.storage.paths import ensure_storage_dirs

if __name__ == '__main__':
    cfg = load_config()
    paths = ensure_storage_dirs(cfg)
    research = run_raw_to_score_pipeline(cfg)
    decision = TradingBot(cfg).build_trade_plan(research['snapshot'])
    write_latest(paths['latest'] / 'trading_decision.json', decision)
    message = build_daily_notification(research, decision)
    notif = send_telegram_message(message)
    write_latest(paths['latest'] / 'telegram_dry_run.json', notif)
    print(json.dumps({'decision': decision, 'telegram': notif}, indent=2, ensure_ascii=False, default=str))
