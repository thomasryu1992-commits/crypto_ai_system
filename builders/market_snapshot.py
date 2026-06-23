from __future__ import annotations

from statistics import mean

from config.settings import MARKET_DATA_PATH, MARKET_SNAPSHOT_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def build_market_snapshot() -> dict:
    data = read_json(MARKET_DATA_PATH, {})
    candles = data.get("candles", [])
    if not candles:
        raise RuntimeError("No candles available. Run market data collector first.")

    closes = [float(c["close"]) for c in candles]
    volumes = [float(c.get("volume", 0)) for c in candles]
    last = candles[-1]
    prev_24 = closes[-25] if len(closes) >= 25 else closes[0]
    last_close = closes[-1]
    change_24h = (last_close - prev_24) / prev_24 if prev_24 else 0.0

    ma20 = _sma(closes, 20)
    ma50 = _sma(closes, 50)
    volume_ma20 = _sma(volumes, 20)
    volume_ratio = volumes[-1] / volume_ma20 if volume_ma20 else 1.0

    derivatives = data.get("derivatives", {})
    funding_rate = float(derivatives.get("funding_rate", 0.0))
    oi_change_24h = float(derivatives.get("open_interest_change_24h", 0.0))

    trend_bias = "neutral"
    if ma20 and ma50 and last_close > ma20 > ma50:
        trend_bias = "bullish"
    elif ma20 and ma50 and last_close < ma20 < ma50:
        trend_bias = "bearish"

    snapshot = {
        "created_at": utc_now_iso(),
        "symbol": data.get("symbol", "BTCUSDT"),
        "timeframe": data.get("timeframe", "1h"),
        "source_type": data.get("source_type", data.get("source", "unknown")),
        "data_quality": data.get("data_quality", "unknown"),
        "is_synthetic": bool(data.get("is_synthetic", False)),
        "is_fallback": bool(data.get("is_fallback", False)),
        "last_candle_time": last.get("timestamp"),
        "last_close": last_close,
        "change_24h_pct": change_24h * 100,
        "ma20": ma20,
        "ma50": ma50,
        "volume_ratio": volume_ratio,
        "funding_rate": funding_rate,
        "open_interest_change_24h": oi_change_24h,
        "trend_bias": trend_bias,
        "candle_count": len(candles),
    }
    atomic_write_json(MARKET_SNAPSHOT_PATH, snapshot)
    log_event("market_snapshot_built", {"trend_bias": trend_bias, "source_type": snapshot["source_type"]})
    return snapshot


def main() -> None:
    snapshot = build_market_snapshot()
    print(f"Market snapshot built: {snapshot['symbol']} trend={snapshot['trend_bias']}")


if __name__ == "__main__":
    main()
