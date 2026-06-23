from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from config.settings import RAW_DIR, STORAGE_DIR, ensure_base_dirs
from scripts.json_utils import load_json, save_json


def save_raw_snapshot(data: Dict[str, Any], category: str, source: str, symbol: str = "BTCUSDT") -> Path:
    ensure_base_dirs()
    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_symbol = symbol.replace("/", "").replace(":", "")
    safe_source = source.replace("/", "_")
    path = RAW_DIR / category / f"{date_label}_{safe_symbol}_{safe_source}.json"
    save_json(path, data)
    return path


def run_raw_store() -> Dict[str, Any]:
    market_context = load_json(STORAGE_DIR / "market_context.json", default={})
    if not isinstance(market_context, dict) or not market_context:
        return {"status": "NO_MARKET_CONTEXT", "saved": False}
    symbol = str(market_context.get("symbol") or "BTCUSDT")
    market_path = save_raw_snapshot(market_context, "market", "market_context", symbol)
    derivatives_path = save_raw_snapshot(market_context.get("derivatives", {}), "derivatives", "coinalyze_safe_template", symbol)
    return {
        "status": "RAW_SNAPSHOT_SAVED",
        "saved": True,
        "files": [str(market_path), str(derivatives_path)],
    }
