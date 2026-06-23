from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("COINALYZE_API_KEY")
    base_url = os.getenv("COINALYZE_BASE_URL", "https://api.coinalyze.net/v1").rstrip("/")
    symbol = os.getenv("COINALYZE_SYMBOL", "BTCUSDT_PERP.A")

    print("=" * 80)
    print("[COINALYZE CONNECTION TEST]")
    print("=" * 80)

    if not api_key or api_key == "your_coinalyze_api_key_here":
        print("Status: ERROR")
        print("Reason: COINALYZE_API_KEY is missing or still uses placeholder value in .env")
        sys.exit(1)

    print("API Key: FOUND")
    print(f"Base URL: {base_url}")
    print(f"Symbol: {symbol}")

    checks = [
        _request(
            name="GET_EXCHANGES",
            url=f"{base_url}/exchanges",
            params={"api_key": api_key},
        ),
        _request(
            name="GET_CURRENT_OPEN_INTEREST",
            url=f"{base_url}/open-interest",
            params={"api_key": api_key, "symbols": symbol, "convert_to_usd": "true"},
        ),
        _request(
            name="GET_CURRENT_FUNDING_RATE",
            url=f"{base_url}/funding-rate",
            params={"api_key": api_key, "symbols": symbol},
        ),
    ]

    failed = [item for item in checks if not item["ok"]]

    print("-" * 80)
    print("[RESULT]")

    for item in checks:
        print(f"{item['name']}: {item['status_code']} / ok={item['ok']} / {item['message']}")

    print("-" * 80)

    if failed:
        print("Final Status: FAILED")
        sys.exit(1)

    print("Final Status: PASSED")


def _request(name: str, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=20)
        ok = 200 <= response.status_code < 300
        message = "OK" if ok else response.text[:300]
        return {"name": name, "ok": ok, "status_code": response.status_code, "message": message}
    except Exception as error:
        return {
            "name": name,
            "ok": False,
            "status_code": None,
            "message": f"{type(error).__name__}: {error}",
        }


if __name__ == "__main__":
    main()
