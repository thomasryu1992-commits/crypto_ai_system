from __future__ import annotations

from statistics import median

from config.settings import ATR_MULTIPLIER, ATR_PERIOD, MAX_STOP_LOSS_BPS, MIN_STOP_LOSS_BPS


def true_range(current: dict, previous_close: float | None) -> float:
    high = float(current["high"])
    low = float(current["low"])
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def calculate_atr(candles: list[dict], period: int = ATR_PERIOD) -> float | None:
    if len(candles) < period + 1:
        return None
    trs = []
    previous_close = None
    for candle in candles[-(period + 1):]:
        trs.append(true_range(candle, previous_close))
        previous_close = float(candle["close"])
    return sum(trs[-period:]) / period


def stop_distance_bps_from_atr(price: float, candles: list[dict]) -> dict:
    atr = calculate_atr(candles)
    if not atr or price <= 0:
        raw_bps = MIN_STOP_LOSS_BPS
    else:
        raw_bps = (atr / price) * 10000 * ATR_MULTIPLIER

    final_bps = min(max(raw_bps, MIN_STOP_LOSS_BPS), MAX_STOP_LOSS_BPS)
    return {
        "atr": atr,
        "raw_stop_distance_bps": round(raw_bps, 4),
        "final_stop_distance_bps": round(final_bps, 4),
        "min_stop_loss_bps": MIN_STOP_LOSS_BPS,
        "max_stop_loss_bps": MAX_STOP_LOSS_BPS,
    }
