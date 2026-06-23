from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
LATEST_DIR = STORAGE_DIR / "latest"
BACKUP_DIR = STORAGE_DIR / "backup"
QUEUE_DIR = STORAGE_DIR / "queue"
LOGS_DIR = STORAGE_DIR / "logs"
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data")
REPORTS_DIR = PROJECT_ROOT / os.getenv("REPORTS_DIR", "reports")
SECRETS_DIR = PROJECT_ROOT / os.getenv("SECRETS_DIR", "secrets")

for _d in [STORAGE_DIR, LATEST_DIR, BACKUP_DIR, QUEUE_DIR, LOGS_DIR, DATA_DIR, REPORTS_DIR, SECRETS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


def _first_env(names: list[str], default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def env_str(names: str | list[str], default: str = "") -> str:
    return _first_env([names] if isinstance(names, str) else names, default)


def env_bool(names: str | list[str], default: bool = False) -> bool:
    raw = env_str(names, "")
    if raw == "":
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on", "enabled"}


def env_float(names: str | list[str], default: float = 0.0) -> float:
    raw = env_str(names, "")
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_int(names: str | list[str], default: int = 0) -> int:
    raw = env_str(names, "")
    if raw == "":
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


APP_ENV = env_str("APP_ENV", "local")
TIMEZONE = env_str("TIMEZONE", "Asia/Ho_Chi_Minh")
REPORT_TIMEZONE = env_str("REPORT_TIMEZONE", "Asia/Seoul")
TRADING_MODE = env_str("TRADING_MODE", "paper").lower()
DRY_RUN = env_bool("DRY_RUN", True)
LOG_LEVEL = env_str("LOG_LEVEL", "INFO")

SYMBOL = env_str(["SYMBOL", "DEFAULT_SYMBOL"], "BTCUSDT")
TIMEFRAME = env_str(["TIMEFRAME", "DEFAULT_TIMEFRAME"], "1h")
DEFAULT_EXCHANGE = env_str("DEFAULT_EXCHANGE", "binance")

# Data source
COINALYZE_ENABLED = env_bool(["COINALYZE_ENABLED", "ENABLE_COINALYZE", "USE_COINALYZE"], False)
COINALYZE_API_KEY = env_str("COINALYZE_API_KEY", "")
BINANCE_MARKET_DATA_ENABLED = env_bool("BINANCE_MARKET_DATA_ENABLED", False)
BINANCE_PUBLIC_BASE_URL = env_str("BINANCE_PUBLIC_BASE_URL", "https://api.binance.com")

# Spreadsheet-first storage
SPREADSHEET_ENABLED = env_bool(["SPREADSHEET_ENABLED", "GOOGLE_SHEETS_ENABLED", "ENABLE_GOOGLE_SHEETS"], False)
SPREADSHEET_PROVIDER = env_str("SPREADSHEET_PROVIDER", "local_csv")  # local_csv | google_sheets
SPREADSHEET_ID = env_str(["SPREADSHEET_ID", "GOOGLE_SHEET_ID", "GOOGLE_SPREADSHEET_ID"], "")
SPREADSHEET_WORKSHEET_PREFIX = env_str("SPREADSHEET_WORKSHEET_PREFIX", "")
GOOGLE_SERVICE_ACCOUNT_FILE = env_str(["GOOGLE_SERVICE_ACCOUNT_FILE", "GOOGLE_APPLICATION_CREDENTIALS"], "")
GOOGLE_SERVICE_ACCOUNT_JSON = env_str(["GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_CREDENTIALS_JSON"], "")
SPREADSHEET_BATCH_SIZE = env_int("SPREADSHEET_BATCH_SIZE", 50)
SPREADSHEET_MAX_RETRY = env_int("SPREADSHEET_MAX_RETRY", 5)

TELEGRAM_ENABLED = env_bool(["TELEGRAM_ENABLED", "ENABLE_TELEGRAM", "ENABLE_TELEGRAM_ALERTS"], False)
TELEGRAM_BOT_TOKEN = env_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = env_str("TELEGRAM_CHAT_ID", "")

# Data health
MAX_STALE_DATA_MINUTES = env_int("MAX_STALE_DATA_MINUTES", 180)
MIN_CANDLE_COUNT = env_int("MIN_CANDLE_COUNT", 50)
EXPECTED_CANDLE_INTERVAL_MINUTES = env_int("EXPECTED_CANDLE_INTERVAL_MINUTES", 60)
MAX_ALLOWED_CANDLE_GAP_MULTIPLE = env_float("MAX_ALLOWED_CANDLE_GAP_MULTIPLE", 1.5)
BLOCK_SYNTHETIC_DATA_FOR_TRADING = env_bool("BLOCK_SYNTHETIC_DATA_FOR_TRADING", True)
BLOCK_FALLBACK_DATA_FOR_TRADING = env_bool("BLOCK_FALLBACK_DATA_FOR_TRADING", True)

# Paper/risk
PAPER_ENGINE_ENABLED = env_bool("PAPER_ENGINE_ENABLED", True)
PAPER_TRADING_ENABLED = env_bool("PAPER_TRADING_ENABLED", True)
RISK_PER_TRADE = env_float("RISK_PER_TRADE", 0.01)
MAX_OPEN_POSITIONS = env_int("MAX_OPEN_POSITIONS", 1)
DAILY_MAX_LOSS_R = env_float(["DAILY_MAX_LOSS_R", "MAX_DAILY_LOSS_R"], -2.0)
WEEKLY_MAX_LOSS_R = env_float(["WEEKLY_MAX_LOSS_R", "MAX_WEEKLY_LOSS_R"], -5.0)
MAX_CONSECUTIVE_LOSSES = env_int("MAX_CONSECUTIVE_LOSSES", 3)
MAX_DRAWDOWN_PCT = env_float("MAX_DRAWDOWN_PCT", -10.0)

# ATR / execution safety
ATR_PERIOD = env_int("ATR_PERIOD", 14)
ATR_MULTIPLIER = env_float("ATR_MULTIPLIER", 1.5)
MIN_STOP_LOSS_BPS = env_float("MIN_STOP_LOSS_BPS", 35.0)
MAX_STOP_LOSS_BPS = env_float("MAX_STOP_LOSS_BPS", 250.0)
POSITION_SIZE_ACCOUNT_EQUITY_USDT = env_float("POSITION_SIZE_ACCOUNT_EQUITY_USDT", 1000.0)
MAX_POSITION_NOTIONAL_USDT = env_float("MAX_POSITION_NOTIONAL_USDT", 100.0)

# Live/testnet guard
EXCHANGE_ORDER_ENABLED = env_bool("EXCHANGE_ORDER_ENABLED", False)
LIVE_TRADING_ENABLED = env_bool("LIVE_TRADING_ENABLED", False)
ALLOW_LIVE_TRADING = env_bool("ALLOW_LIVE_TRADING", False)
ENABLE_REAL_ORDERS = env_bool("ENABLE_REAL_ORDERS", False)
ENABLE_TESTNET_ORDERS = env_bool("ENABLE_TESTNET_ORDERS", False)
LIVE_TRADING_CONFIRMATION = env_str("LIVE_TRADING_CONFIRMATION", "")
LIVE_TRADING_CONFIRMATION_PHRASE = env_str("LIVE_TRADING_CONFIRMATION_PHRASE", "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS")

BINANCE_API_KEY = env_str("BINANCE_API_KEY", "")
BINANCE_API_SECRET = env_str("BINANCE_API_SECRET", "")
BINANCE_TESTNET = env_bool("BINANCE_TESTNET", True)
BINANCE_TESTNET_BASE_URL = env_str("BINANCE_TESTNET_BASE_URL", "https://testnet.binancefuture.com")

MAX_LIVE_POSITION_USDT = env_float("MAX_LIVE_POSITION_USDT", 20.0)
MAX_ORDER_NOTIONAL_USDT = env_float("MAX_ORDER_NOTIONAL_USDT", 20.0)
MAX_DAILY_LOSS_USDT = env_float("MAX_DAILY_LOSS_USDT", 10.0)
MAX_WEEKLY_LOSS_USDT = env_float("MAX_WEEKLY_LOSS_USDT", 30.0)
MAX_LIVE_TRADES_PER_DAY = env_int("MAX_LIVE_TRADES_PER_DAY", 3)

LIVE_SHADOW_MODE = env_bool("LIVE_SHADOW_MODE", True)
SLIPPAGE_ASSUMPTION_BPS = env_float("SLIPPAGE_ASSUMPTION_BPS", 8.0)
FEE_ASSUMPTION_BPS = env_float("FEE_ASSUMPTION_BPS", 4.0)
LATENCY_ASSUMPTION_MS = env_int("LATENCY_ASSUMPTION_MS", 750)

# Latest JSON cache paths
MARKET_DATA_PATH = LATEST_DIR / "coinalyze_market_data.json"
MARKET_SNAPSHOT_PATH = LATEST_DIR / "market_snapshot.json"
MARKET_CONTEXT_PATH = LATEST_DIR / "market_context.json"
RESEARCH_RESULT_PATH = LATEST_DIR / "research_cycle_result.json"
RESEARCH_DECISION_PATH = LATEST_DIR / "research_decision_result.json"
TRADING_CYCLE_PATH = LATEST_DIR / "trading_cycle_result.json"
PAPER_STATE_PATH = LATEST_DIR / "paper_state.json"
DATA_HEALTH_PATH = LATEST_DIR / "data_health_report.json"
RISK_STATUS_PATH = LATEST_DIR / "risk_status.json"
TRADE_DECISION_PATH = LATEST_DIR / "latest_trade_decision.json"
ORDER_INTENT_PATH = LATEST_DIR / "latest_order_intent.json"
ORDER_RESULT_PATH = LATEST_DIR / "latest_order_result.json"
RECONCILIATION_PATH = LATEST_DIR / "latest_reconciliation.json"
LIVE_READINESS_PATH = LATEST_DIR / "live_readiness_check.json"
LIVE_SHADOW_REPORT_PATH = LATEST_DIR / "live_shadow_report.json"
LIMITED_LIVE_READINESS_REPORT_PATH = LATEST_DIR / "limited_live_readiness_report.json"
SCHEDULER_HEALTH_PATH = LATEST_DIR / "scheduler_health_result.json"

# History / backup / queue
EVENT_LOG_PATH = LOGS_DIR / "event_log.jsonl"
SPREADSHEET_RETRY_QUEUE_PATH = QUEUE_DIR / "spreadsheet_retry_queue.jsonl"
SPREADSHEET_DEAD_LETTER_PATH = QUEUE_DIR / "spreadsheet_dead_letter.jsonl"
SPREADSHEET_SYNC_RESULT_PATH = LATEST_DIR / "spreadsheet_sync_result.json"
SPREADSHEET_LOCAL_BACKUP_DIR = BACKUP_DIR / "spreadsheet"
PAPER_TRADES_PATH = LATEST_DIR / "paper_trades.json"
PAPER_TRADES_CSV_PATH = BACKUP_DIR / "paper_trades.csv"
FORWARD_TEST_LOG_PATH = LOGS_DIR / "forward_test_log.jsonl"
FORWARD_TEST_SUMMARY_PATH = LATEST_DIR / "forward_test_summary.json"
TESTNET_ORDER_LOG_PATH = LOGS_DIR / "testnet_order_log.jsonl"
STEP150_VALIDATION_PATH = LATEST_DIR / "step150_validation_result.json"

if LIVE_TRADING_ENABLED and TRADING_MODE == "live":
    if LIVE_TRADING_CONFIRMATION != LIVE_TRADING_CONFIRMATION_PHRASE:
        raise RuntimeError("LIVE_TRADING_CONFIRMATION mismatch. Real live trading remains blocked.")
