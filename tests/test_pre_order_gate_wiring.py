"""B-3: the real PreOrderRiskGate authorises order intents.

Paper gets an approved paper profile -> the gate approves a valid signal.
Non-paper stages get no approved profile -> the gate blocks (fail-closed), so
signed-testnet/live can never auto-create an order intent from the pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.research.active_research_signal import build_active_research_signal
from crypto_ai_system.research.paper_profile import PAPER_PROFILE_SHA256, get_paper_profile
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate


def _signal():
    snap = {
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
    research = {"scenario": "Bullish", "signal_timing": "Early", "scores": {"final_score": 0.7}}
    return build_active_research_signal(snap, research)


def _gate(*, stage, profile):
    return evaluate_pre_order_risk_gate(
        decision={"decision_id": "d1", "side": "LONG", "direction": "LONG", "entry": 100000.0},
        research_signal=_signal(),
        profile=profile,
        runtime_state={"stage": stage, "open_positions": 0},
        market_state={"price": 100000.0},
        gate_config={"stage": stage, "max_open_positions": 1, "require_profile_hash": True},
    )


def test_paper_profile_is_approved_and_hash_stable():
    p = get_paper_profile()
    assert p["approved"] is True
    assert p["profile_sha256"] == PAPER_PROFILE_SHA256
    # Deterministic across calls.
    assert get_paper_profile()["profile_sha256"] == PAPER_PROFILE_SHA256


def test_paper_stage_gate_approves_valid_signal():
    result = _gate(stage="paper", profile=get_paper_profile())
    assert result.approved is True, result.block_reasons
    assert result.status == "PASS_PAPER"
    assert result.risk_gate_id
    # Signal profile hash matches the approved profile (profile-hash gate passes).
    assert not any("PROFILE_HASH" in b for b in result.block_reasons)


def test_signed_testnet_without_approved_profile_blocks():
    # The bridge supplies NO profile for non-paper stages -> fail-closed.
    result = _gate(stage="signed_testnet", profile={})
    assert result.approved is False
    assert result.status == "BLOCK_PROFILE_UNAPPROVED"


def test_synthetic_signal_blocks_even_with_paper_profile():
    snap_research = _signal()
    snap_research["synthetic_used"] = True
    result = evaluate_pre_order_risk_gate(
        decision={"decision_id": "d1", "side": "LONG", "direction": "LONG"},
        research_signal=snap_research,
        profile=get_paper_profile(),
        runtime_state={"stage": "paper"},
        market_state={"price": 100000.0},
        gate_config={"stage": "paper"},
    )
    assert result.approved is False
    assert result.status == "BLOCK_FALLBACK_OR_SYNTHETIC"
