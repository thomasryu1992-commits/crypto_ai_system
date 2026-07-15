"""E-1 (directive §7.2): a missing/failed optional metric must carry a status,
never be silently coerced to a genuine-looking 0.0."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import collectors.real_market_data as rmd
from collectors.real_market_data import (
    STATUS_AVAILABLE,
    STATUS_MISSING,
    STATUS_NEUTRAL_DUE_TO_MISSING,
    STATUS_UNAVAILABLE,
    _oi_change_24h,
    _optional_metric,
)


# -- pure metric extraction ---------------------------------------------

def test_optional_metric_available():
    frame = pd.DataFrame([{"funding_rate": 0.0001}])
    value, status, reason = _optional_metric(lambda: frame, lambda f: f.iloc[-1]["funding_rate"])
    assert value == 0.0001
    assert status == STATUS_AVAILABLE
    assert reason is None


def test_optional_metric_api_error_is_unavailable():
    def boom():
        raise RuntimeError("network")

    value, status, reason = _optional_metric(boom, lambda f: f.iloc[-1]["x"])
    assert value is None
    assert status == STATUS_UNAVAILABLE
    assert reason == "api_error"


def test_optional_metric_empty_is_missing():
    value, status, reason = _optional_metric(lambda: pd.DataFrame(), lambda f: f.iloc[-1]["x"])
    assert value is None
    assert status == STATUS_MISSING


# -- OI 24h change ------------------------------------------------------

class _Client:
    def __init__(self, hist_rows):
        self._hist = hist_rows

    def open_interest_hist(self, symbol, period, limit):
        return pd.DataFrame(self._hist)


def test_oi_change_computed_from_history():
    client = _Client([{"open_interest": 100.0}, {"open_interest": 110.0}])
    value, status, reason = _oi_change_24h(client, "BTCUSDT")
    assert abs(value - 0.1) < 1e-9
    assert status == STATUS_AVAILABLE


def test_oi_change_insufficient_history_is_neutral():
    client = _Client([{"open_interest": 100.0}])
    value, status, reason = _oi_change_24h(client, "BTCUSDT")
    assert value is None
    assert status == STATUS_NEUTRAL_DUE_TO_MISSING
    assert reason == "insufficient_history"


def test_oi_change_zero_baseline_is_neutral():
    client = _Client([{"open_interest": 0.0}, {"open_interest": 5.0}])
    value, status, reason = _oi_change_24h(client, "BTCUSDT")
    assert value is None
    assert status == STATUS_NEUTRAL_DUE_TO_MISSING


# -- full collector integration -----------------------------------------

class _FakeClient:
    def __init__(self, *, base_url=None, **kw):
        pass

    def klines(self, symbol, interval, limit):
        return pd.DataFrame(
            [{"timestamp": i, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 5} for i in range(3)]
        )

    def funding_rate(self, symbol, limit):
        return pd.DataFrame([{"funding_rate": 0.0002}])

    def open_interest_now(self, symbol):
        raise RuntimeError("oi endpoint down")

    def open_interest_hist(self, symbol, period, limit):
        return pd.DataFrame([{"open_interest": 200.0}, {"open_interest": 220.0}])


def test_collect_real_market_data_carries_health(monkeypatch):
    monkeypatch.setattr(rmd, "BinanceFuturesPublicClient", _FakeClient)
    data = rmd.collect_real_market_data("BTC-PERP", "PT1H")

    health = data["optional_data_health"]
    assert health["funding_rate"]["status"] == STATUS_AVAILABLE
    assert health["funding_rate"]["value"] == 0.0002
    # OI now endpoint raised -> unavailable, numeric coerced to 0.0 but flagged.
    assert health["open_interest"]["status"] == STATUS_UNAVAILABLE
    assert data["derivatives"]["open_interest"] == 0.0
    # OI change really computed (not hardcoded 0.0).
    assert health["open_interest_change_24h"]["status"] == STATUS_AVAILABLE
    assert abs(data["derivatives"]["open_interest_change_24h"] - 0.1) < 1e-9
