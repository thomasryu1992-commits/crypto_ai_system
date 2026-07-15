"""Network-free tests for real market-data mapping and synthetic detection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from collectors.real_market_data import to_binance_interval, to_binance_symbol
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


def test_looks_synthetic_uses_flags_not_key_names():
    real = {"is_synthetic": False, "is_fallback": False, "data_quality": "real"}
    synthetic = {"is_synthetic": True, "is_fallback": True, "data_quality": "synthetic"}
    assert _looks_synthetic(real) is False
    assert _looks_synthetic(synthetic) is True
    # Missing/unknown quality is treated as not-real (fail-closed).
    assert _looks_synthetic({}) is True
    assert _looks_synthetic("not a dict") is True
