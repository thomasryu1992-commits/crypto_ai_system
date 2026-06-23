from __future__ import annotations

from datetime import timedelta
from typing import Any

from config.settings import (
    BLOCK_FALLBACK_DATA_FOR_TRADING,
    BLOCK_SYNTHETIC_DATA_FOR_TRADING,
    DATA_HEALTH_PATH,
    EXPECTED_CANDLE_INTERVAL_MINUTES,
    MARKET_DATA_PATH,
    MARKET_SNAPSHOT_PATH,
    MAX_ALLOWED_CANDLE_GAP_MULTIPLE,
    MAX_STALE_DATA_MINUTES,
    MIN_CANDLE_COUNT,
)
from core.json_io import atomic_write_json, read_json
from core.time_utils import parse_time, utc_now, utc_now_iso
from core.event_log import log_event


def _validate_ohlcv(candle: dict[str, Any], idx: int) -> list[str]:
    problems = []
    try:
        o = float(candle["open"])
        h = float(candle["high"])
        l = float(candle["low"])
        c = float(candle["close"])
        v = float(candle.get("volume", 0))
    except Exception:
        return [f"invalid_ohlcv_numeric_at_{idx}"]

    if h < max(o, c) or l > min(o, c) or h < l:
        problems.append(f"invalid_ohlc_logic_at_{idx}")
    if v <= 0:
        problems.append(f"non_positive_volume_at_{idx}")
    return problems


def run_data_health_check() -> dict:
    data = read_json(MARKET_DATA_PATH, {})
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})

    problems: list[str] = []
    warnings: list[str] = []
    candles = data.get("candles", [])

    if len(candles) < MIN_CANDLE_COUNT:
        problems.append("insufficient_candle_count")

    if data.get("is_synthetic") and BLOCK_SYNTHETIC_DATA_FOR_TRADING:
        problems.append("synthetic_data_source_blocks_trading")
    if data.get("is_fallback") and BLOCK_FALLBACK_DATA_FOR_TRADING:
        problems.append("fallback_data_source_blocks_trading")

    last_time = parse_time(candles[-1].get("timestamp")) if candles else None
    if last_time is None:
        problems.append("missing_latest_candle_time")
    else:
        age_minutes = (utc_now() - last_time).total_seconds() / 60
        if age_minutes > MAX_STALE_DATA_MINUTES:
            problems.append("stale_market_data")
    # Timestamp gap check
    parsed_times = [parse_time(c.get("timestamp")) for c in candles]
    parsed_times = [t for t in parsed_times if t is not None]
    if len(parsed_times) >= 2:
        expected = timedelta(minutes=EXPECTED_CANDLE_INTERVAL_MINUTES).total_seconds()
        max_gap = expected * MAX_ALLOWED_CANDLE_GAP_MULTIPLE
        for i in range(1, len(parsed_times)):
            gap = (parsed_times[i] - parsed_times[i - 1]).total_seconds()
            if gap > max_gap:
                problems.append(f"candle_gap_detected_at_index_{i}")
                break
            if gap <= 0:
                problems.append(f"non_increasing_timestamp_at_index_{i}")
                break

    # OHLCV validation
    for idx, candle in enumerate(candles[-min(len(candles), 200):]):
        problems.extend(_validate_ohlcv(candle, idx))

    # Snapshot/source consistency
    if snapshot:
        if snapshot.get("source_type") != data.get("source_type"):
            warnings.append("snapshot_source_differs_from_market_data")
        if snapshot.get("is_synthetic") != data.get("is_synthetic"):
            warnings.append("snapshot_synthetic_flag_differs_from_market_data")
    else:
        problems.append("missing_market_snapshot")

    status = "HEALTHY"
    allow_trading = True
    if warnings:
        status = "WARNING"
    if problems:
        status = "UNHEALTHY"
        allow_trading = False

    result = {
        "created_at": utc_now_iso(),
        "status": status,
        "allow_trading": allow_trading,
        "problems": sorted(set(problems)),
        "warnings": sorted(set(warnings)),
        "source_type": data.get("source_type", data.get("source", "unknown")),
        "data_quality": data.get("data_quality", "unknown"),
        "is_synthetic": bool(data.get("is_synthetic", False)),
        "is_fallback": bool(data.get("is_fallback", False)),
        "candle_count": len(candles),
        "latest_candle_time": candles[-1].get("timestamp") if candles else None,
    }
    atomic_write_json(DATA_HEALTH_PATH, result)
    log_event("data_health_checked", {"status": status, "allow_trading": allow_trading, "problems": result["problems"]})
    return result


def main() -> None:
    result = run_data_health_check()
    print(f"Data Health: {result['status']} allow_trading={result['allow_trading']}")


if __name__ == "__main__":
    main()
