"""Network-free tests for real market-data mapping and synthetic detection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from collectors.real_market_data import (
    drop_forming_candle,
    to_binance_interval,
    to_binance_symbol,
)
from crypto_ai_system.pipeline.data_agent import _looks_synthetic


def test_symbol_mapping():
    assert to_binance_symbol("BTC-PERP") == "BTCUSDT"
    assert to_binance_symbol("ETH-PERP") == "ETHUSDT"
    assert to_binance_symbol("BTCUSDT") == "BTCUSDT"
    assert to_binance_symbol("btc/usdt") == "BTCUSDT"


def test_interval_mapping():
    assert to_binance_interval("PT1H") == "1h"
    assert to_binance_interval("PT15M") == "15m"
    assert to_binance_interval("P1D") == "1d"
    assert to_binance_interval("UNKNOWN") == "1h"  # safe default


def _candle(open_time, price=100.0):
    return {"timestamp": open_time.isoformat(), "open": price, "high": price + 1,
            "low": price - 1, "close": price, "volume": 10.0}


def test_forming_candle_is_dropped():
    from datetime import timedelta

    from core.time_utils import utc_now

    now = utc_now()
    candles = [
        _candle(now - timedelta(hours=3)),
        _candle(now - timedelta(hours=2)),
        _candle(now - timedelta(minutes=30)),  # 1h bar opened 30min ago: forming
    ]
    out = drop_forming_candle(candles, "1h")
    assert len(out) == 2
    assert out[-1]["timestamp"] == candles[1]["timestamp"]


def test_closed_last_candle_is_kept():
    from datetime import timedelta

    from core.time_utils import utc_now

    now = utc_now()
    candles = [
        _candle(now - timedelta(hours=3)),
        _candle(now - timedelta(hours=2, minutes=1)),  # closed >1h ago
    ]
    assert drop_forming_candle(candles, "1h") == candles


def test_unparseable_last_timestamp_drops_fail_closed():
    candles = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        {"timestamp": "garbage", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    ]
    assert len(drop_forming_candle(candles, "1h")) == 1


def test_single_candle_is_never_dropped():
    candles = [{"timestamp": "garbage", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
    assert drop_forming_candle(candles, "1h") == candles


def test_looks_synthetic_uses_flags_not_key_names():
    real = {"is_synthetic": False, "is_fallback": False, "data_quality": "real"}
    synthetic = {"is_synthetic": True, "is_fallback": True, "data_quality": "synthetic"}
    assert _looks_synthetic(real) is False
    assert _looks_synthetic(synthetic) is True
    # Missing/unknown quality is treated as not-real (fail-closed).
    assert _looks_synthetic({}) is True
    assert _looks_synthetic("not a dict") is True
