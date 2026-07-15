"""E-2: the active pipeline emits a ResearchSignal v2 with a real lineage chain
and a trade_permission derived from the active research."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.research.active_research_signal import build_active_research_signal


def _snapshot(**over):
    base = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "last_candle_time": "2026-07-15T00:00:00Z",
        "last_close": 100000.0,
        "funding_rate": 0.0001,
        "open_interest_change_24h": 0.02,
        "source_type": "binance_futures_public",
        "is_synthetic": False,
        "is_fallback": False,
        "ma20": 99000.0,
        "ma50": 98000.0,
        "volume_ratio": 1.2,
        "change_24h_pct": 1.5,
        "trend_bias": "bullish",
        "optional_data_health": {
            "funding_rate": {"status": "available"},
            "open_interest": {"status": "available"},
            "open_interest_change_24h": {"status": "available"},
        },
    }
    base.update(over)
    return base


def _research(**over):
    base = {"scenario": "Bullish", "signal_timing": "Early", "signal_quality": "High", "scores": {"final_score": 0.7}}
    base.update(over)
    return base


def test_signal_has_full_lineage_chain():
    sig = build_active_research_signal(_snapshot(), _research(), cycle_id="cycle_abc")
    for key in ("research_signal_id", "data_snapshot_id", "feature_snapshot_id", "feature_matrix_sha256", "profile_id"):
        assert sig.get(key), f"missing {key}"
    assert sig["cycle_id"] == "cycle_abc"
    assert sig["research_signal_id"] == sig["signal_id"]


def test_lineage_is_content_stable():
    a = build_active_research_signal(_snapshot(), _research(), cycle_id="c1")
    b = build_active_research_signal(_snapshot(), _research(), cycle_id="c2")
    # Same candle + features -> same lineage ids regardless of cycle id.
    assert a["research_signal_id"] == b["research_signal_id"]
    assert a["feature_matrix_sha256"] == b["feature_matrix_sha256"]


def test_bullish_permits_long():
    sig = build_active_research_signal(_snapshot(), _research(scenario="Bullish", signal_timing="Early"))
    tp = sig["trade_permission"]
    assert tp["allow_long"] is True
    assert tp["allow_new_position"] is True
    assert tp["risk_level"] == "normal"
    assert sig["entry_side"] == "LONG"


def test_synthetic_data_blocks_permission():
    sig = build_active_research_signal(_snapshot(is_synthetic=True), _research())
    tp = sig["trade_permission"]
    assert tp["allow_new_position"] is False
    assert "SYNTHETIC_DATA" in tp["block_reasons"]
    assert sig["synthetic_used"] is True
    assert sig["data_quality_status"] == "SYNTHETIC"
    assert sig["live_candidate_eligible"] is False


def test_missing_optional_data_flagged_not_hidden():
    snap = _snapshot(optional_data_health={
        "funding_rate": {"status": "available"},
        "open_interest": {"status": "unavailable"},
        "open_interest_change_24h": {"status": "neutral_due_to_missing"},
    })
    sig = build_active_research_signal(snap, _research())
    assert sig["missing_optional_data_neutral"] is True
    assert sig["live_candidate_eligible"] is False
    # Missing optional data does NOT block a long on real data (neutral, not fatal).
    assert sig["trade_permission"]["allow_long"] is True


def test_neutral_scenario_blocks_new_position():
    sig = build_active_research_signal(_snapshot(), _research(scenario="Neutral", signal_timing="Late"))
    assert sig["trade_permission"]["allow_new_position"] is False
    assert sig["entry_side"] == "FLAT"
