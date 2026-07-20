"""Snapshot freshness: is_stale must reflect real candle age (QA fix).

The PreOrderRiskGate's DATA_FRESHNESS check reads the snapshot's is_stale via
the bridges; before this fix the builder never wrote the key, so every input to
the freshness gate was constant-False and the check could not fire.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import builders.market_snapshot as ms
from core.time_utils import utc_now


def _candles(last_age_minutes: float, count: int = 30) -> list[dict]:
    end = utc_now() - timedelta(minutes=last_age_minutes)
    out = []
    for i in range(count):
        ts = end - timedelta(hours=count - 1 - i)
        out.append({"timestamp": ts.isoformat(), "open": 100.0, "high": 101.0,
                    "low": 99.0, "close": 100.0, "volume": 10.0})
    return out


def _build(monkeypatch, candles):
    written = {}
    monkeypatch.setattr(ms, "read_json", lambda path, default: {"symbol": "BTCUSDT", "candles": candles})
    monkeypatch.setattr(ms, "atomic_write_json", lambda path, payload: written.update(payload))
    monkeypatch.setattr(ms, "log_event", lambda *a, **k: None)
    return ms.build_market_snapshot()


def test_fresh_candle_is_not_stale(monkeypatch) -> None:
    snap = _build(monkeypatch, _candles(last_age_minutes=5))
    assert snap["is_stale"] is False
    assert snap["last_candle_age_minutes"] < ms.MAX_STALE_DATA_MINUTES


def test_old_candle_is_stale(monkeypatch) -> None:
    snap = _build(monkeypatch, _candles(last_age_minutes=ms.MAX_STALE_DATA_MINUTES + 60))
    assert snap["is_stale"] is True


def test_unparseable_timestamp_fails_closed_as_stale(monkeypatch) -> None:
    candles = _candles(last_age_minutes=5)
    candles[-1]["timestamp"] = "not-a-time"
    snap = _build(monkeypatch, candles)
    assert snap["is_stale"] is True
    assert snap["last_candle_age_minutes"] is None
