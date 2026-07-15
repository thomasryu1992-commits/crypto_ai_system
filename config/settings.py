from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

# Dotenv loading is explicit; importing this module must not mutate process state.
def load_project_dotenv(path: str | Path | None = None) -> bool:
    return load_dotenv(path) if path is not None else load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
LATEST_DIR = STORAGE_DIR / "latest"
BACKUP_DIR = STORAGE_DIR / "backup"
QUEUE_DIR = STORAGE_DIR / "queue"
LOGS_DIR = STORAGE_DIR / "logs"
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data")
REPORTS_DIR = PROJECT_ROOT / os.getenv("REPORTS_DIR", "reports")
SECRETS_DIR = PROJECT_ROOT / os.getenv("SECRETS_DIR", "secrets")

RUNTIME_DIRECTORIES = [STORAGE_DIR, LATEST_DIR, BACKUP_DIR, QUEUE_DIR, LOGS_DIR, DATA_DIR, REPORTS_DIR, SECRETS_DIR]

def ensure_runtime_directories() -> list[Path]:
    """Create runtime directories explicitly from runner/bootstrap code, not at import time."""
    for directory in RUNTIME_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)
    return list(RUNTIME_DIRECTORIES)


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

SYMBOL = env_str(["SYMBOL", "DEFAULT_SYMBOL", "DEFAULT_CANONICAL_SYMBOL"], "BTC-PERP")
TIMEFRAME = env_str(["TIMEFRAME", "DEFAULT_TIMEFRAME"], "PT1H")
DEFAULT_EXCHANGE = env_str("DEFAULT_EXCHANGE", "extended")

# Data source
COINALYZE_ENABLED = env_bool(["COINALYZE_ENABLED", "ENABLE_COINALYZE", "USE_COINALYZE"], False)
COINALYZE_API_KEY = env_str("COINALYZE_API_KEY", "")
BINANCE_MARKET_DATA_ENABLED = env_bool("BINANCE_MARKET_DATA_ENABLED", False)  # legacy-only; Extended is default
BINANCE_PUBLIC_BASE_URL = env_str("BINANCE_PUBLIC_BASE_URL", "https://api.binance.com")
# Real market data via Binance USD-M Futures public endpoints (no API key
# required, read-only). When enabled the collector fetches real candles and
# falls back to synthetic only if the fetch fails.
REAL_MARKET_DATA_ENABLED = env_bool(["REAL_MARKET_DATA_ENABLED", "USE_REAL_MARKET_DATA"], True)
BINANCE_FUTURES_PUBLIC_BASE_URL = env_str("BINANCE_FUTURES_PUBLIC_BASE_URL", "https://fapi.binance.com")

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
USE_RESEARCH_SIGNAL_GATE = env_bool("USE_RESEARCH_SIGNAL_GATE", True)
RISK_LEVEL_REDUCED_POSITION_MULTIPLIER = env_float("RISK_LEVEL_REDUCED_POSITION_MULTIPLIER", 0.5)
RISK_LEVEL_BLOCKED_POSITION_MULTIPLIER = env_float("RISK_LEVEL_BLOCKED_POSITION_MULTIPLIER", 0.0)
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
POSITION_SIZE_ACCOUNT_EQUITY_USDC = env_float("POSITION_SIZE_ACCOUNT_EQUITY_USDC", POSITION_SIZE_ACCOUNT_EQUITY_USDT)
MAX_POSITION_NOTIONAL_USDC = env_float("MAX_POSITION_NOTIONAL_USDC", MAX_POSITION_NOTIONAL_USDT)

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
MAX_LIVE_POSITION_USDC = env_float("MAX_LIVE_POSITION_USDC", MAX_LIVE_POSITION_USDT)
MAX_ORDER_NOTIONAL_USDC = env_float("MAX_ORDER_NOTIONAL_USDC", MAX_ORDER_NOTIONAL_USDT)
MAX_DAILY_LOSS_USDC = env_float("MAX_DAILY_LOSS_USDC", MAX_DAILY_LOSS_USDT)
MAX_WEEKLY_LOSS_USDC = env_float("MAX_WEEKLY_LOSS_USDC", MAX_WEEKLY_LOSS_USDT)
TESTNET_SIGNED_ORDER_ENABLED = env_bool("TESTNET_SIGNED_ORDER_ENABLED", False)
SIGNED_TESTNET_ADAPTER_CONTRACT_ENABLED = env_bool("SIGNED_TESTNET_ADAPTER_CONTRACT_ENABLED", False)
SIGNED_TESTNET_PLACE_ORDER_ENABLED = env_bool("SIGNED_TESTNET_PLACE_ORDER_ENABLED", False)
SIGNED_TESTNET_MANUAL_APPROVAL_REQUIRED = env_bool("SIGNED_TESTNET_MANUAL_APPROVAL_REQUIRED", True)
SIGNED_TESTNET_REQUIRE_TESTNET_KEY_SCOPE = env_bool("SIGNED_TESTNET_REQUIRE_TESTNET_KEY_SCOPE", True)
SIGNED_TESTNET_LIVE_KEY_ALLOWED = env_bool("SIGNED_TESTNET_LIVE_KEY_ALLOWED", False)
SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT = env_float("SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT", 5.0)
SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT = env_int("SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT", 3)
MAX_LIVE_TRADES_PER_DAY = env_int("MAX_LIVE_TRADES_PER_DAY", 3)

# Strategy factory live routing. Shadow mode records what the active pool would
# do each cycle without changing any order; it never drives execution on its own.
STRATEGY_FACTORY_ROUTING_ENABLED = env_bool("STRATEGY_FACTORY_ROUTING_ENABLED", False)

# Live canary preparation (read-only probe; grants no order authority)
LIVE_READONLY_PROBE_ENABLED = env_bool("LIVE_READONLY_PROBE_ENABLED", False)
LIVE_BINANCE_API_KEY = env_str("LIVE_BINANCE_API_KEY", "")
LIVE_BINANCE_API_SECRET = env_str("LIVE_BINANCE_API_SECRET", "")
LIVE_BINANCE_FUTURES_BASE_URL = env_str("LIVE_BINANCE_FUTURES_BASE_URL", "https://fapi.binance.com")
LIVE_BINANCE_SPOT_BASE_URL = env_str("LIVE_BINANCE_SPOT_BASE_URL", "https://api.binance.com")
LIVE_CANARY_MIN_CLEAN_TESTNET_SESSIONS = env_int("LIVE_CANARY_MIN_CLEAN_TESTNET_SESSIONS", 5)

LIVE_SHADOW_MODE = env_bool("LIVE_SHADOW_MODE", True)
SLIPPAGE_ASSUMPTION_BPS = env_float("SLIPPAGE_ASSUMPTION_BPS", 8.0)
FEE_ASSUMPTION_BPS = env_float("FEE_ASSUMPTION_BPS", 4.0)
LATENCY_ASSUMPTION_MS = env_int("LATENCY_ASSUMPTION_MS", 750)

# Latest JSON cache paths
MARKET_DATA_PATH = LATEST_DIR / "coinalyze_market_data.json"
MARKET_SNAPSHOT_PATH = LATEST_DIR / "market_snapshot.json"
MARKET_CONTEXT_PATH = LATEST_DIR / "market_context.json"
ACTIVE_STRATEGY_POOL_PATH = LATEST_DIR / "active_strategy_pool.json"
STRATEGY_ROUTING_PATH = LATEST_DIR / "strategy_routing.json"
RESEARCH_RESULT_PATH = LATEST_DIR / "research_cycle_result.json"
RESEARCH_SIGNAL_PATH = LATEST_DIR / "research_signal.json"
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
PERMISSION_GATE_AUDIT_PATH = LOGS_DIR / "permission_gate_audit.jsonl"
LATEST_PERMISSION_GATE_AUDIT_PATH = LATEST_DIR / "permission_gate_audit_latest.json"
PAPER_RISK_LEVEL_REPORT_PATH = LATEST_DIR / "paper_risk_level_report.json"

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



class RuntimeSettings:
    """Backward-compatible settings object for legacy modules."""

    # Core paths
    project_root = PROJECT_ROOT
    storage_dir = STORAGE_DIR
    latest_dir = LATEST_DIR
    backup_dir = BACKUP_DIR
    queue_dir = QUEUE_DIR
    logs_dir = LOGS_DIR
    data_dir = DATA_DIR
    reports_dir = REPORTS_DIR
    secrets_dir = SECRETS_DIR

    # App/runtime
    app_env = APP_ENV
    timezone = TIMEZONE
    report_timezone = REPORT_TIMEZONE
    trading_mode = TRADING_MODE
    dry_run = DRY_RUN
    log_level = LOG_LEVEL
    symbol = SYMBOL
    timeframe = TIMEFRAME
    default_exchange = DEFAULT_EXCHANGE

    # Telegram
    telegram_enabled = TELEGRAM_ENABLED
    telegram_bot_token = TELEGRAM_BOT_TOKEN
    telegram_chat_id = TELEGRAM_CHAT_ID

    # Spreadsheet
    spreadsheet_enabled = SPREADSHEET_ENABLED
    spreadsheet_provider = SPREADSHEET_PROVIDER
    spreadsheet_id = SPREADSHEET_ID
    google_service_account_file = GOOGLE_SERVICE_ACCOUNT_FILE
    google_service_account_json = GOOGLE_SERVICE_ACCOUNT_JSON

    # Data sources
    coinalyze_enabled = COINALYZE_ENABLED
    coinalyze_api_key = COINALYZE_API_KEY
    binance_market_data_enabled = BINANCE_MARKET_DATA_ENABLED

    # Risk / execution safety
    paper_engine_enabled = PAPER_ENGINE_ENABLED
    paper_trading_enabled = PAPER_TRADING_ENABLED
    risk_per_trade = RISK_PER_TRADE
    max_open_positions = MAX_OPEN_POSITIONS
    live_trading_enabled = LIVE_TRADING_ENABLED
    enable_real_orders = ENABLE_REAL_ORDERS
    testnet_signed_order_enabled = TESTNET_SIGNED_ORDER_ENABLED
    signed_testnet_adapter_contract_enabled = SIGNED_TESTNET_ADAPTER_CONTRACT_ENABLED
    signed_testnet_place_order_enabled = SIGNED_TESTNET_PLACE_ORDER_ENABLED
    signed_testnet_manual_approval_required = SIGNED_TESTNET_MANUAL_APPROVAL_REQUIRED
    signed_testnet_require_testnet_key_scope = SIGNED_TESTNET_REQUIRE_TESTNET_KEY_SCOPE
    signed_testnet_live_key_allowed = SIGNED_TESTNET_LIVE_KEY_ALLOWED
    signed_testnet_max_order_notional_usdt = SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT
    signed_testnet_max_daily_order_count = SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT


settings = RuntimeSettings()

def validate_live_trading_confirmation() -> None:
    """Validate live-trading confirmation explicitly at runtime, not during import."""
    if LIVE_TRADING_ENABLED and TRADING_MODE == "live":
        if LIVE_TRADING_CONFIRMATION != LIVE_TRADING_CONFIRMATION_PHRASE:
            raise RuntimeError("LIVE_TRADING_CONFIRMATION mismatch. Real live trading remains blocked.")
