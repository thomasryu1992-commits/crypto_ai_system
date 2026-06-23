from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
RAW_DERIVATIVES_DIR = KNOWLEDGE_BASE_DIR / ".raw" / "derivatives"

COINALYZE_MARKET_DATA_PATH = STORAGE_DIR / "coinalyze_market_data.json"


def collect_real_market_data() -> Dict[str, Any]:
    """
    Step 52: Real Market Data Collector

    Collects Coinalyze derivatives data and stores:
    - knowledge_base/.raw/derivatives/YYYY-MM-DD_SYMBOL_coinalyze.json
    - storage/coinalyze_market_data.json

    Safety:
    - This file only reads market data.
    - It does not place orders.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DERIVATIVES_DIR.mkdir(parents=True, exist_ok=True)

    enabled = _env_bool("REAL_MARKET_DATA_ENABLED", False)

    if not enabled:
        result = {
            "step": "STEP_52_REAL_MARKET_DATA_COLLECTOR",
            "status": "SKIPPED",
            "reason": "REAL_MARKET_DATA_ENABLED=false",
            "timestamp_utc": _now_utc_iso(),
        }
        _save_json(COINALYZE_MARKET_DATA_PATH, result)
        return result

    api_key = os.getenv("COINALYZE_API_KEY")
    base_url = os.getenv("COINALYZE_BASE_URL", "https://api.coinalyze.net/v1").rstrip("/")
    symbol = os.getenv("COINALYZE_SYMBOL", "BTCUSDT_PERP.A")
    exchange = os.getenv("COINALYZE_EXCHANGE", "binance")
    interval = os.getenv("COINALYZE_INTERVAL", "1hour")
    lookback_hours = _env_int("COINALYZE_LOOKBACK_HOURS", 48)

    if not api_key or api_key == "your_coinalyze_api_key_here":
        result = {
            "step": "STEP_52_REAL_MARKET_DATA_COLLECTOR",
            "status": "ERROR",
            "error_type": "MissingAPIKey",
            "error_message": "COINALYZE_API_KEY is missing or placeholder.",
            "timestamp_utc": _now_utc_iso(),
        }
        _save_json(COINALYZE_MARKET_DATA_PATH, result)
        return result

    now_ts = int(time.time())
    from_ts = now_ts - (lookback_hours * 60 * 60)

    common_history_params = {
        "symbols": symbol,
        "interval": interval,
        "from": from_ts,
        "to": now_ts,
    }

    responses = {
        "current_open_interest": _get(
            base_url=base_url,
            api_key=api_key,
            path="/open-interest",
            params={"symbols": symbol, "convert_to_usd": "true"},
        ),
        "current_funding_rate": _get(
            base_url=base_url,
            api_key=api_key,
            path="/funding-rate",
            params={"symbols": symbol},
        ),
        "current_predicted_funding_rate": _get(
            base_url=base_url,
            api_key=api_key,
            path="/predicted-funding-rate",
            params={"symbols": symbol},
        ),
        "ohlcv_history": _get(
            base_url=base_url,
            api_key=api_key,
            path="/ohlcv-history",
            params=common_history_params,
        ),
        "open_interest_history": _get(
            base_url=base_url,
            api_key=api_key,
            path="/open-interest-history",
            params={**common_history_params, "convert_to_usd": "true"},
        ),
        "funding_rate_history": _get(
            base_url=base_url,
            api_key=api_key,
            path="/funding-rate-history",
            params=common_history_params,
        ),
        "liquidation_history": _get(
            base_url=base_url,
            api_key=api_key,
            path="/liquidation-history",
            params={**common_history_params, "convert_to_usd": "true"},
        ),
        "long_short_ratio_history": _get(
            base_url=base_url,
            api_key=api_key,
            path="/long-short-ratio-history",
            params=common_history_params,
        ),
    }

    ok_count = len([item for item in responses.values() if item.get("ok")])
    error_count = len(responses) - ok_count
    status = "COLLECTED" if ok_count > 0 else "ERROR"

    raw_filename = f"{_today_utc()}_{_sanitize_filename(symbol)}_coinalyze.json"
    raw_path = RAW_DERIVATIVES_DIR / raw_filename

    result = {
        "step": "STEP_52_REAL_MARKET_DATA_COLLECTOR",
        "status": status,
        "timestamp_utc": _now_utc_iso(),
        "provider": "coinalyze",
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval,
        "lookback_hours": lookback_hours,
        "from_ts": from_ts,
        "to_ts": now_ts,
        "summary": {
            "endpoint_count": len(responses),
            "ok_count": ok_count,
            "error_count": error_count,
        },
        "responses": responses,
        "files": {
            "raw_path": str(raw_path),
            "coinalyze_market_data": str(COINALYZE_MARKET_DATA_PATH),
        },
    }

    _save_json(raw_path, result)
    _save_json(COINALYZE_MARKET_DATA_PATH, result)

    return result


def _get(base_url: str, api_key: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{base_url}{path}"
    request_params = {**params, "api_key": api_key}

    try:
        response = requests.get(url, params=request_params, timeout=30)
        ok = 200 <= response.status_code < 300

        try:
            data = response.json()
        except ValueError:
            data = response.text

        return {
            "ok": ok,
            "status_code": response.status_code,
            "path": path,
            "url": url,
            "data": data,
            "error_message": None if ok else str(data)[:500],
        }
    except Exception as error:
        return {
            "ok": False,
            "status_code": None,
            "path": path,
            "url": url,
            "data": None,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "yes", "y", "on"}


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def main() -> None:
    result = collect_real_market_data()
    print("=" * 80)
    print("[REAL MARKET DATA COLLECTOR]")
    print("=" * 80)
    print(f"Status: {result.get('status')}")
    print(f"Provider: {result.get('provider')}")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Interval: {result.get('interval')}")

    summary = result.get("summary", {})
    print(f"OK Endpoints: {summary.get('ok_count')}")
    print(f"Error Endpoints: {summary.get('error_count')}")

    files = result.get("files", {})
    print("-" * 80)
    print("[FILES]")
    for key, value in files.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
