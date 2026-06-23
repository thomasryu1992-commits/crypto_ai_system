from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"

MARKET_SNAPSHOT_PATH = STORAGE_DIR / "market_snapshot.json"
DYNAMIC_SETUP_RESULT_PATH = STORAGE_DIR / "dynamic_setup_result.json"
DYNAMIC_SETUP_LOG_PATH = STORAGE_DIR / "dynamic_setup_log.json"


def generate_dynamic_setup(
    market_snapshot_path: str | Path = MARKET_SNAPSHOT_PATH,
    storage_dir: str | Path = STORAGE_DIR,
) -> Dict[str, Any]:
    """
    Step 61:
    Dynamic Setup Generator

    Purpose:
    - Read real-time market_snapshot.json.
    - Score long / short setup quality.
    - Generate dynamic conditional setup.
    - Avoid creating setup when signals are weak or overcrowded.
    - Save dynamic_setup_result.json.
    - Append dynamic_setup_log.json.

    This module does not place orders.
    It only generates a research setup candidate.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    result_path = storage_path / "dynamic_setup_result.json"
    log_path = storage_path / "dynamic_setup_log.json"

    started_at = _now_utc_iso()

    try:
        market_snapshot = _load_json(Path(market_snapshot_path), default={})

        if not isinstance(market_snapshot, dict) or not market_snapshot:
            result = _build_error_result(
                started_at=started_at,
                error_type="MissingMarketSnapshot",
                error_message="market_snapshot.json is missing or empty.",
                market_snapshot={},
            )
            _save_json(result_path, result)
            _append_log(log_path, result)
            return result

        current_price = _extract_current_price(market_snapshot)

        if current_price is None or current_price <= 0:
            result = _build_error_result(
                started_at=started_at,
                error_type="MissingCurrentPrice",
                error_message="current_price is missing from market_snapshot.json.",
                market_snapshot=market_snapshot,
            )
            _save_json(result_path, result)
            _append_log(log_path, result)
            return result

        signals = _extract_signals(market_snapshot)

        long_score, long_reasons = _score_long_setup(signals)
        short_score, short_reasons = _score_short_setup(signals)

        direction, setup_type, selected_score, selected_reasons = _select_direction(
            long_score=long_score,
            short_score=short_score,
            long_reasons=long_reasons,
            short_reasons=short_reasons,
            signals=signals,
        )

        min_score = _env_float("DYNAMIC_SETUP_MIN_SCORE", 2.0)

        if direction == "observe_only" or selected_score < min_score:
            result = {
                "step": "STEP_61_DYNAMIC_SETUP_GENERATOR",
                "status": "OBSERVE_ONLY",
                "decision_type": "OBSERVE_ONLY",
                "timestamp_utc": _now_utc_iso(),
                "started_at_utc": started_at,
                "finished_at_utc": _now_utc_iso(),
                "symbol": market_snapshot.get("symbol", "BTCUSDT"),
                "current_price": current_price,
                "confidence": "low",
                "long_score": long_score,
                "short_score": short_score,
                "selected_score": selected_score,
                "signals": signals,
                "reasoning": selected_reasons,
                "reason": (
                    "Signal score is too weak or market structure is too mixed. "
                    "No conditional setup was created."
                ),
                "conditional_setup": None,
                "safety": {
                    "order_execution": False,
                    "paper_watch_created": False,
                    "live_trading_enabled": False,
                },
                "files": {
                    "market_snapshot": str(market_snapshot_path),
                    "dynamic_setup_result": str(result_path),
                    "dynamic_setup_log": str(log_path),
                },
            }

            _save_json(result_path, result)
            _append_log(log_path, result)
            return result

        confidence = _confidence_from_score(selected_score)
        conditional_setup = _build_conditional_setup(
            symbol=market_snapshot.get("symbol", "BTCUSDT"),
            current_price=current_price,
            direction=direction,
            setup_type=setup_type,
            confidence=confidence,
            score=selected_score,
            signals=signals,
        )

        result = {
            "step": "STEP_61_DYNAMIC_SETUP_GENERATOR",
            "status": "DYNAMIC_SETUP_CREATED",
            "decision_type": "CONDITIONAL_WATCH",
            "timestamp_utc": _now_utc_iso(),
            "started_at_utc": started_at,
            "finished_at_utc": _now_utc_iso(),
            "symbol": market_snapshot.get("symbol", "BTCUSDT"),
            "current_price": current_price,
            "direction": direction,
            "setup_type": setup_type,
            "confidence": confidence,
            "long_score": long_score,
            "short_score": short_score,
            "selected_score": selected_score,
            "signals": signals,
            "reasoning": selected_reasons,
            "conditional_setup": conditional_setup,
            "market_snapshot_summary": _compact_market_snapshot(market_snapshot),
            "safety": {
                "order_execution": False,
                "paper_watch_created": False,
                "live_trading_enabled": False,
            },
            "files": {
                "market_snapshot": str(market_snapshot_path),
                "dynamic_setup_result": str(result_path),
                "dynamic_setup_log": str(log_path),
            },
        }

        _save_json(result_path, result)
        _append_log(log_path, result)

        return result

    except Exception as error:
        result = _build_error_result(
            started_at=started_at,
            error_type=type(error).__name__,
            error_message=str(error),
            market_snapshot={},
            traceback_text=traceback.format_exc(),
        )

        _save_json(result_path, result)
        _append_log(log_path, result)

        return result


def _extract_current_price(market_snapshot: Dict[str, Any]) -> Optional[float]:
    candidates = [
        market_snapshot.get("current_price"),
        market_snapshot.get("price"),
    ]

    market_data = market_snapshot.get("market_data")

    if isinstance(market_data, dict):
        price_data = market_data.get("price")

        if isinstance(price_data, dict):
            candidates.extend([
                price_data.get("current"),
                price_data.get("value"),
            ])

    for value in candidates:
        parsed = _to_float(value)

        if parsed is not None:
            return parsed

    return None


def _extract_signals(market_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    market_data = market_snapshot.get("market_data")

    if not isinstance(market_data, dict):
        market_data = {}

    price = _safe_dict(market_data.get("price"))
    open_interest = _safe_dict(market_data.get("open_interest"))
    funding_rate = _safe_dict(market_data.get("funding_rate"))
    long_short_ratio = _safe_dict(market_data.get("long_short_ratio"))
    liquidation = _safe_dict(market_data.get("liquidation"))

    return {
        "price": {
            "signal": price.get("signal", "unknown"),
            "change_lookback_pct": price.get("change_lookback_pct"),
            "current": price.get("current"),
        },
        "open_interest": {
            "signal": open_interest.get("signal", "unknown"),
            "value": open_interest.get("value"),
            "change_lookback_pct": open_interest.get("change_lookback_pct"),
        },
        "funding_rate": {
            "signal": funding_rate.get("signal", "unknown"),
            "value": funding_rate.get("value"),
            "predicted_value": funding_rate.get("predicted_value"),
        },
        "long_short_ratio": {
            "signal": long_short_ratio.get("signal", "unknown"),
            "value": long_short_ratio.get("value"),
            "long": long_short_ratio.get("long"),
            "short": long_short_ratio.get("short"),
        },
        "liquidation": {
            "signal": liquidation.get("signal", "unknown"),
            "dominant_side": liquidation.get("dominant_side"),
            "long_liquidation": liquidation.get("long_liquidation"),
            "short_liquidation": liquidation.get("short_liquidation"),
            "total_liquidation": liquidation.get("total_liquidation"),
        },
    }


def _score_long_setup(signals: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    price_signal = _signal(signals, "price")
    oi_signal = _signal(signals, "open_interest")
    funding_signal = _signal(signals, "funding_rate")
    long_short_signal = _signal(signals, "long_short_ratio")
    liquidation_signal = _signal(signals, "liquidation")

    if price_signal == "strong_up":
        score += 3
        reasons.append("LONG +3: price signal is strong_up.")
    elif price_signal == "mild_up":
        score += 2
        reasons.append("LONG +2: price signal is mild_up.")
    elif price_signal == "flat":
        score += 0.5
        reasons.append("LONG +0.5: price is flat, still acceptable for reclaim watch.")
    elif price_signal in {"mild_down", "strong_down"}:
        score -= 1
        reasons.append(f"LONG -1: price signal is {price_signal}.")

    if oi_signal == "rising_fast":
        score += 3
        reasons.append("LONG +3: open interest is rising_fast.")
    elif oi_signal == "rising":
        score += 2
        reasons.append("LONG +2: open interest is rising.")
    elif oi_signal in {"falling", "falling_fast"}:
        score -= 1
        reasons.append(f"LONG -1: open interest is {oi_signal}.")

    if funding_signal in {"neutral", "slightly_negative"}:
        score += 1
        reasons.append(f"LONG +1: funding is {funding_signal}, not overheated.")
    elif funding_signal == "slightly_positive":
        score += 0.5
        reasons.append("LONG +0.5: funding is slightly_positive.")
    elif funding_signal == "overheated_positive":
        score -= 2
        reasons.append("LONG -2: funding is overheated_positive.")
    elif funding_signal == "deep_negative":
        score += 0.5
        reasons.append("LONG +0.5: funding is deep_negative, possible squeeze fuel.")

    if long_short_signal == "long_crowded":
        score -= 2
        reasons.append("LONG -2: long/short ratio is long_crowded.")
    elif long_short_signal == "mild_long_bias":
        score += 0.5
        reasons.append("LONG +0.5: mild long bias.")
    elif long_short_signal == "short_crowded":
        score += 1
        reasons.append("LONG +1: short_crowded, possible short squeeze fuel.")

    if liquidation_signal == "short_liquidation_dominant":
        score += 1
        reasons.append("LONG +1: short liquidation is dominant.")
    elif liquidation_signal == "long_liquidation_dominant":
        score -= 1
        reasons.append("LONG -1: long liquidation is dominant.")

    return round(score, 3), reasons


def _score_short_setup(signals: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    price_signal = _signal(signals, "price")
    oi_signal = _signal(signals, "open_interest")
    funding_signal = _signal(signals, "funding_rate")
    long_short_signal = _signal(signals, "long_short_ratio")
    liquidation_signal = _signal(signals, "liquidation")

    if price_signal == "strong_down":
        score += 3
        reasons.append("SHORT +3: price signal is strong_down.")
    elif price_signal == "mild_down":
        score += 2
        reasons.append("SHORT +2: price signal is mild_down.")
    elif price_signal == "flat":
        score += 0.5
        reasons.append("SHORT +0.5: price is flat, possible breakdown watch.")
    elif price_signal in {"mild_up", "strong_up"}:
        score -= 1
        reasons.append(f"SHORT -1: price signal is {price_signal}.")

    if oi_signal == "rising_fast":
        score += 3
        reasons.append("SHORT +3: open interest is rising_fast.")
    elif oi_signal == "rising":
        score += 2
        reasons.append("SHORT +2: open interest is rising.")
    elif oi_signal in {"falling", "falling_fast"}:
        score -= 1
        reasons.append(f"SHORT -1: open interest is {oi_signal}.")

    if funding_signal == "overheated_positive":
        score += 1.5
        reasons.append("SHORT +1.5: funding is overheated_positive.")
    elif funding_signal == "slightly_positive":
        score += 1
        reasons.append("SHORT +1: funding is slightly_positive.")
    elif funding_signal == "deep_negative":
        score -= 2
        reasons.append("SHORT -2: funding is deep_negative.")
    elif funding_signal == "slightly_negative":
        score -= 0.5
        reasons.append("SHORT -0.5: funding is slightly_negative.")

    if long_short_signal == "long_crowded":
        score += 1
        reasons.append("SHORT +1: long_crowded, possible long squeeze risk.")
    elif long_short_signal == "short_crowded":
        score -= 2
        reasons.append("SHORT -2: short_crowded.")
    elif long_short_signal == "mild_short_bias":
        score += 0.5
        reasons.append("SHORT +0.5: mild short bias.")

    if liquidation_signal == "long_liquidation_dominant":
        score += 1
        reasons.append("SHORT +1: long liquidation is dominant.")
    elif liquidation_signal == "short_liquidation_dominant":
        score -= 1
        reasons.append("SHORT -1: short liquidation is dominant.")

    return round(score, 3), reasons


def _select_direction(
    long_score: float,
    short_score: float,
    long_reasons: List[str],
    short_reasons: List[str],
    signals: Dict[str, Any],
) -> Tuple[str, str, float, List[str]]:
    price_signal = _signal(signals, "price")
    funding_signal = _signal(signals, "funding_rate")
    long_short_signal = _signal(signals, "long_short_ratio")

    if funding_signal == "overheated_positive" and long_short_signal == "long_crowded":
        if short_score >= 2:
            return "short", "overheated_long_reversal", short_score, [
                "Selected SHORT because funding is overheated and long positioning is crowded.",
                *short_reasons,
            ]

        return "observe_only", "observe_only", 0.0, [
            "Market is overheated and long crowded, but short score is not strong enough.",
            *long_reasons,
            *short_reasons,
        ]

    if funding_signal == "deep_negative" and long_short_signal == "short_crowded":
        if long_score >= 2:
            return "long", "short_squeeze_reclaim", long_score, [
                "Selected LONG because funding is deeply negative and short positioning is crowded.",
                *long_reasons,
            ]

        return "observe_only", "observe_only", 0.0, [
            "Market is deeply negative and short crowded, but long score is not strong enough.",
            *long_reasons,
            *short_reasons,
        ]

    score_gap = abs(long_score - short_score)

    if score_gap < 1.0:
        return "observe_only", "range_watch", max(long_score, short_score), [
            "Long and short scores are too close. Market is mixed.",
            f"price_signal={price_signal}",
            f"long_score={long_score}",
            f"short_score={short_score}",
        ]

    if long_score > short_score:
        return "long", "breakout_reclaim", long_score, long_reasons

    return "short", "breakdown_continuation", short_score, short_reasons


def _build_conditional_setup(
    symbol: Any,
    current_price: float,
    direction: str,
    setup_type: str,
    confidence: str,
    score: float,
    signals: Dict[str, Any],
) -> Dict[str, Any]:
    expires_after_hours = _env_int("FALLBACK_EXPIRES_AFTER_HOURS", 24)

    long_trigger_pct = _env_float("DYNAMIC_LONG_TRIGGER_PCT", 0.003)
    long_invalidation_pct = _env_float("DYNAMIC_LONG_INVALIDATION_PCT", 0.008)
    long_take_profit_pct = _env_float("DYNAMIC_LONG_TAKE_PROFIT_PCT", 0.015)

    short_trigger_pct = _env_float("DYNAMIC_SHORT_TRIGGER_PCT", 0.003)
    short_invalidation_pct = _env_float("DYNAMIC_SHORT_INVALIDATION_PCT", 0.008)
    short_take_profit_pct = _env_float("DYNAMIC_SHORT_TAKE_PROFIT_PCT", 0.015)

    if direction == "long":
        trigger_price = current_price * (1 + long_trigger_pct)
        invalidation_price = current_price * (1 - long_invalidation_pct)
        take_profit = current_price * (1 + long_take_profit_pct)
    elif direction == "short":
        trigger_price = current_price * (1 - short_trigger_pct)
        invalidation_price = current_price * (1 + short_invalidation_pct)
        take_profit = current_price * (1 - short_take_profit_pct)
    else:
        raise ValueError(f"Unsupported direction for conditional setup: {direction}")

    return {
        "symbol": str(symbol or "BTCUSDT"),
        "setup_type": setup_type,
        "direction": direction,
        "trigger_price": _round_price(trigger_price),
        "invalidation_price": _round_price(invalidation_price),
        "take_profit": _round_price(take_profit),
        "expires_after_hours": expires_after_hours,
        "confidence": confidence,
        "score": score,
        "source": "dynamic_setup_generator",
        "created_at_utc": _now_utc_iso(),
        "base_price": _round_price(current_price),
        "rules": {
            "long_trigger_pct": long_trigger_pct,
            "long_invalidation_pct": long_invalidation_pct,
            "long_take_profit_pct": long_take_profit_pct,
            "short_trigger_pct": short_trigger_pct,
            "short_invalidation_pct": short_invalidation_pct,
            "short_take_profit_pct": short_take_profit_pct,
        },
        "signals": signals,
    }


def _confidence_from_score(score: float) -> str:
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _signal(signals: Dict[str, Any], key: str) -> str:
    item = signals.get(key)

    if not isinstance(item, dict):
        return "unknown"

    return str(item.get("signal") or "unknown")


def _compact_market_snapshot(market_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": market_snapshot.get("status"),
        "symbol": market_snapshot.get("symbol"),
        "source_symbol": market_snapshot.get("source_symbol"),
        "provider": market_snapshot.get("provider"),
        "current_price": market_snapshot.get("current_price"),
        "timestamp_utc": market_snapshot.get("timestamp_utc"),
        "data_quality": market_snapshot.get("data_quality"),
        "raw_source": market_snapshot.get("raw_source"),
    }


def _build_error_result(
    started_at: str,
    error_type: str,
    error_message: str,
    market_snapshot: Dict[str, Any],
    traceback_text: Optional[str] = None,
) -> Dict[str, Any]:
    result = {
        "step": "STEP_61_DYNAMIC_SETUP_GENERATOR",
        "status": "ERROR",
        "decision_type": "NO_DECISION",
        "timestamp_utc": _now_utc_iso(),
        "started_at_utc": started_at,
        "finished_at_utc": _now_utc_iso(),
        "error_type": error_type,
        "error_message": error_message,
        "conditional_setup": None,
        "market_snapshot_summary": _compact_market_snapshot(market_snapshot),
        "safety": {
            "order_execution": False,
            "paper_watch_created": False,
            "live_trading_enabled": False,
        },
        "files": {
            "market_snapshot": str(MARKET_SNAPSHOT_PATH),
            "dynamic_setup_result": str(DYNAMIC_SETUP_RESULT_PATH),
            "dynamic_setup_log": str(DYNAMIC_SETUP_LOG_PATH),
        },
    }

    if traceback_text:
        result["traceback"] = traceback_text

    return result


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _env_float(key: str, default: float) -> float:
    value = os.getenv(key)

    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _round_price(value: float) -> float:
    decimals = _env_int("DYNAMIC_SETUP_PRICE_DECIMALS", 2)
    return round(float(value), decimals)


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


def _append_log(path: Path, item: Dict[str, Any], max_items: int = 500) -> None:
    existing = _load_json(path, default=[])

    if not isinstance(existing, list):
        existing = []

    existing.append(item)
    existing = existing[-max_items:]

    _save_json(path, existing)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    result = generate_dynamic_setup()

    print("=" * 90)
    print("[DYNAMIC SETUP GENERATOR]")
    print("=" * 90)
    print(f"Status: {result.get('status')}")
    print(f"Decision Type: {result.get('decision_type')}")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Current Price: {result.get('current_price')}")
    print(f"Direction: {result.get('direction')}")
    print(f"Setup Type: {result.get('setup_type')}")
    print(f"Confidence: {result.get('confidence')}")
    print(f"Long Score: {result.get('long_score')}")
    print(f"Short Score: {result.get('short_score')}")
    print(f"Selected Score: {result.get('selected_score')}")

    conditional_setup = result.get("conditional_setup")

    print("-" * 90)
    print("[CONDITIONAL SETUP]")

    if isinstance(conditional_setup, dict):
        print(f"Trigger Price: {conditional_setup.get('trigger_price')}")
        print(f"Invalidation Price: {conditional_setup.get('invalidation_price')}")
        print(f"Take Profit: {conditional_setup.get('take_profit')}")
        print(f"Expires After Hours: {conditional_setup.get('expires_after_hours')}")
    else:
        print("None")

    print("-" * 90)
    print("[REASONING]")

    reasoning = result.get("reasoning")

    if isinstance(reasoning, list):
        for item in reasoning[:12]:
            print(f"- {item}")
    else:
        print(result.get("reason"))

    print("-" * 90)
    print("[FILES]")
    files = result.get("files", {})

    if isinstance(files, dict):
        for key, value in files.items():
            print(f"{key}: {value}")

    print("=" * 90)


if __name__ == "__main__":
    main()