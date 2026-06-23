from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"

COINALYZE_MARKET_DATA_PATH = STORAGE_DIR / "coinalyze_market_data.json"
MARKET_SNAPSHOT_PATH = STORAGE_DIR / "market_snapshot.json"
MARKET_CONTEXT_PATH = STORAGE_DIR / "market_context.json"


def build_market_snapshot() -> Dict[str, Any]:
    """
    Step 52: Market Snapshot Builder

    Reads:
    - storage/coinalyze_market_data.json

    Writes:
    - storage/market_snapshot.json
    - storage/market_context.json
    """

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    coinalyze_data = _load_json(COINALYZE_MARKET_DATA_PATH, default={})

    if not isinstance(coinalyze_data, dict) or coinalyze_data.get("status") not in {"COLLECTED", "PARTIAL"}:
        result = {
            "step": "STEP_52_MARKET_SNAPSHOT_BUILDER",
            "status": "SKIPPED_OR_ERROR",
            "timestamp_utc": _now_utc_iso(),
            "error_message": "coinalyze_market_data.json is missing, skipped, or invalid.",
            "coinalyze_status": coinalyze_data.get("status") if isinstance(coinalyze_data, dict) else None,
        }
        _save_json(MARKET_SNAPSHOT_PATH, result)
        return result

    responses = coinalyze_data.get("responses", {})
    if not isinstance(responses, dict):
        responses = {}

    symbol = coinalyze_data.get("symbol", "BTCUSDT_PERP.A")
    timestamp_utc = _now_utc_iso()

    ohlcv_history = _extract_history(responses, "ohlcv_history")
    oi_history = _extract_history(responses, "open_interest_history")
    funding_history = _extract_history(responses, "funding_rate_history")
    liquidation_history = _extract_history(responses, "liquidation_history")
    long_short_history = _extract_history(responses, "long_short_ratio_history")

    latest_ohlcv = _latest(ohlcv_history)
    first_ohlcv = _first(ohlcv_history)

    current_price = _to_float(latest_ohlcv.get("c")) if latest_ohlcv else None
    first_price = _to_float(first_ohlcv.get("c")) if first_ohlcv else None
    price_change_pct = _pct_change(first_price, current_price)

    current_oi = _extract_current_value(responses, "current_open_interest")
    latest_oi_from_history = _to_float(_latest(oi_history).get("c")) if _latest(oi_history) else None
    first_oi_from_history = _to_float(_first(oi_history).get("c")) if _first(oi_history) else None
    oi_value = current_oi if current_oi is not None else latest_oi_from_history
    oi_change_pct = _pct_change(first_oi_from_history, latest_oi_from_history)

    current_funding = _extract_current_value(responses, "current_funding_rate")
    current_predicted_funding = _extract_current_value(responses, "current_predicted_funding_rate")
    latest_funding_from_history = _to_float(_latest(funding_history).get("c")) if _latest(funding_history) else None
    funding_value = current_funding if current_funding is not None else latest_funding_from_history

    latest_long_short = _latest(long_short_history)
    long_short_ratio = _to_float(latest_long_short.get("r")) if latest_long_short else None
    long_ratio = _to_float(latest_long_short.get("l")) if latest_long_short else None
    short_ratio = _to_float(latest_long_short.get("s")) if latest_long_short else None

    liquidation_summary = _summarize_liquidations(liquidation_history)

    snapshot = {
        "step": "STEP_52_MARKET_SNAPSHOT_BUILDER",
        "status": "MARKET_SNAPSHOT_CREATED" if current_price is not None else "MARKET_SNAPSHOT_PARTIAL",
        "timestamp_utc": timestamp_utc,
        "symbol": _normalize_symbol(symbol),
        "source_symbol": symbol,
        "provider": "coinalyze",
        "current_price": current_price,
        "market_data": {
            "price": {"current": current_price, "change_lookback_pct": price_change_pct, "signal": _price_signal(price_change_pct)},
            "open_interest": {"value": oi_value, "change_lookback_pct": oi_change_pct, "signal": _oi_signal(oi_change_pct)},
            "funding_rate": {"value": funding_value, "predicted_value": current_predicted_funding, "signal": _funding_signal(funding_value)},
            "long_short_ratio": {"value": long_short_ratio, "long": long_ratio, "short": short_ratio, "signal": _long_short_signal(long_short_ratio)},
            "liquidation": liquidation_summary,
        },
        "raw_source": {
            "coinalyze_market_data": str(COINALYZE_MARKET_DATA_PATH),
            "raw_path": coinalyze_data.get("files", {}).get("raw_path") if isinstance(coinalyze_data.get("files"), dict) else None,
        },
        "data_quality": {
            "has_price": current_price is not None,
            "has_open_interest": oi_value is not None,
            "has_funding": funding_value is not None,
            "has_long_short_ratio": long_short_ratio is not None,
            "has_liquidation": liquidation_summary.get("total_liquidation") is not None,
        },
    }

    market_context = {
        "symbol": _normalize_symbol(symbol),
        "current_price": current_price,
        "price": current_price,
        "timestamp_utc": timestamp_utc,
        "source": "market_snapshot_builder",
        "market_data": snapshot["market_data"],
        "raw_source": snapshot["raw_source"],
    }

    _save_json(MARKET_SNAPSHOT_PATH, snapshot)
    if current_price is not None:
        _save_json(MARKET_CONTEXT_PATH, market_context)

    return snapshot


def _extract_history(responses: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    item = responses.get(key, {})
    if not isinstance(item, dict) or not item.get("ok"):
        return []
    data = item.get("data")
    if not isinstance(data, list) or not data:
        return []
    first_item = data[0]
    if not isinstance(first_item, dict):
        return []
    history = first_item.get("history")
    if not isinstance(history, list):
        return []
    return [row for row in history if isinstance(row, dict)]


def _extract_current_value(responses: Dict[str, Any], key: str) -> Optional[float]:
    item = responses.get(key, {})
    if not isinstance(item, dict) or not item.get("ok"):
        return None
    data = item.get("data")
    if not isinstance(data, list) or not data:
        return None
    first_item = data[0]
    if not isinstance(first_item, dict):
        return None
    return _to_float(first_item.get("value"))


def _summarize_liquidations(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not history:
        return {"long_liquidation": None, "short_liquidation": None, "total_liquidation": None, "dominant_side": "unknown", "signal": "unknown"}

    long_liq = sum((_to_float(row.get("l")) or 0.0) for row in history)
    short_liq = sum((_to_float(row.get("s")) or 0.0) for row in history)
    total = long_liq + short_liq

    if total <= 0:
        dominant_side = "unknown"
    elif long_liq > short_liq * 1.2:
        dominant_side = "long_liquidation_dominant"
    elif short_liq > long_liq * 1.2:
        dominant_side = "short_liquidation_dominant"
    else:
        dominant_side = "balanced"

    return {"long_liquidation": round(long_liq, 4), "short_liquidation": round(short_liq, 4), "total_liquidation": round(total, 4), "dominant_side": dominant_side, "signal": dominant_side}


def _price_signal(change_pct: Optional[float]) -> str:
    if change_pct is None: return "unknown"
    if change_pct >= 2: return "strong_up"
    if change_pct > 0: return "mild_up"
    if change_pct <= -2: return "strong_down"
    if change_pct < 0: return "mild_down"
    return "flat"


def _oi_signal(change_pct: Optional[float]) -> str:
    if change_pct is None: return "unknown"
    if change_pct >= 3: return "rising_fast"
    if change_pct > 0: return "rising"
    if change_pct <= -3: return "falling_fast"
    if change_pct < 0: return "falling"
    return "flat"


def _funding_signal(value: Optional[float]) -> str:
    if value is None: return "unknown"
    if value >= 0.0005: return "overheated_positive"
    if value > 0: return "slightly_positive"
    if value <= -0.0005: return "deep_negative"
    if value < 0: return "slightly_negative"
    return "neutral"


def _long_short_signal(value: Optional[float]) -> str:
    if value is None: return "unknown"
    if value >= 1.2: return "long_crowded"
    if value > 1.0: return "mild_long_bias"
    if value <= 0.8: return "short_crowded"
    if value < 1.0: return "mild_short_bias"
    return "balanced"


def _normalize_symbol(symbol: str) -> str:
    if str(symbol).startswith("BTC"):
        return "BTCUSDT"
    return str(symbol)


def _latest(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    return history[-1] if history else {}


def _first(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    return history[0] if history else {}


def _pct_change(start: Optional[float], end: Optional[float]) -> Optional[float]:
    if start is None or end is None or start == 0:
        return None
    return round(((end - start) / start) * 100, 6)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    result = build_market_snapshot()
    print("=" * 80)
    print("[MARKET SNAPSHOT BUILDER]")
    print("=" * 80)
    print(f"Status: {result.get('status')}")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Current Price: {result.get('current_price')}")

    market_data = result.get("market_data", {})
    print("-" * 80)
    print("[SIGNALS]")
    print(f"Price: {market_data.get('price', {}).get('signal')}")
    print(f"Open Interest: {market_data.get('open_interest', {}).get('signal')}")
    print(f"Funding: {market_data.get('funding_rate', {}).get('signal')}")
    print(f"Long/Short: {market_data.get('long_short_ratio', {}).get('signal')}")
    print(f"Liquidation: {market_data.get('liquidation', {}).get('signal')}")
    print("-" * 80)
    print("[FILES]")
    print(f"market_snapshot: {MARKET_SNAPSHOT_PATH}")
    print(f"market_context: {MARKET_CONTEXT_PATH}")


if __name__ == "__main__":
    main()
