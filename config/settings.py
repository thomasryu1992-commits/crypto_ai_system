from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


def load_env_file(path: str | Path = ".env") -> Dict[str, str]:
    env_path = Path(path)
    loaded: Dict[str, str] = {}
    if not env_path.exists():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


load_env_file()


class Settings:
    STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "storage"))
    TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()
    DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
    SYMBOL = os.getenv("SYMBOL", "BTCUSDT_PERP.A")
    INTERVAL = os.getenv("INTERVAL", "1hour")
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")
    DAILY_REPORT_TIME = os.getenv("DAILY_REPORT_TIME", "19:00")

    ENABLE_COINALYZE = os.getenv("ENABLE_COINALYZE", "false").lower() == "true"
    COINALYZE_API_KEY = os.getenv("COINALYZE_API_KEY", "")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    ENABLE_SPREADSHEET_SYNC = os.getenv("ENABLE_SPREADSHEET_SYNC", "true").lower() == "true"
    SPREADSHEET_LOCAL_EXPORT = os.getenv("SPREADSHEET_LOCAL_EXPORT", "true").lower() == "true"


def ensure_storage_dirs() -> None:
    for subdir in [
        Settings.STORAGE_DIR,
        Settings.STORAGE_DIR / "raw_data",
        Settings.STORAGE_DIR / "reports",
        Settings.STORAGE_DIR / "logs",
        Settings.STORAGE_DIR / "scheduler_logs",
    ]:
        Path(subdir).mkdir(parents=True, exist_ok=True)


def storage_path(filename: str) -> Path:
    ensure_storage_dirs()
    return Settings.STORAGE_DIR / filename
