"""L4: live profile, signal profile resolution, and the strategy bridge's live gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.research import live_profile as lp
from crypto_ai_system.research.paper_profile import PAPER_PROFILE_ID, PAPER_PROFILE_SHA256

CONFIRM = "I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY"


def _configure_live(monkeypatch, **overrides):
    values = {
        "LIVE_STRATEGY_ORDER_ENABLED": True,
        "LIVE_STRATEGY_PLACE_ORDER_ENABLED": True,
        "LIVE_STRATEGY_MANUAL_KILL_SWITCH": False,
        "LIVE_STRATEGY_CONFIRMATION": CONFIRM,
        "LIVE_STRATEGY_CONFIRMATION_PHRASE": CONFIRM,
        "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT": 60.0,
        "LIVE_STRATEGY_ABSOLUTE_MAX_NOTIONAL_USDT": 200.0,
        "LIVE_STRATEGY_MAX_DAILY_ORDER_COUNT": 5,
        "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT": 20.0,
    }
    values.update(overrides)
    for name, val in values.items():
        monkeypatch.setattr(settings, name, val, raising=False)


@pytest.fixture
def promoted(monkeypatch):
    import crypto_ai_system.execution.live_promotion as promo
    monkeypatch.setattr(promo, "live_promotion_ready", lambda *a, **k: True)


# -- live profile ---------------------------------------------------------------

def test_live_profile_unapproved_by_default():
    profile = lp.get_live_profile()
    assert profile["approved"] is False
    assert profile["approval_status"] == "unapproved"
    # Identity hash is static regardless of approval state.
    assert profile["profile_sha256"] == lp.LIVE_PROFILE_SHA256


def test_live_profile_approved_when_configured(monkeypatch, promoted):
    _configure_live(monkeypatch)
    profile = lp.get_live_profile()
    assert profile["approved"] is True
    assert profile["approved_stages"] == ["live"]


def test_block_reason_for_missing_loss_limit(monkeypatch, promoted):
    _configure_live(monkeypatch, LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT=0.0)
    assert "DAILY_LOSS_LIMIT" in lp.live_stage_block_reason()


def test_block_reason_for_missing_cap(monkeypatch, promoted):
    _configure_live(monkeypatch, LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT=0.0)
    assert "MAX_ORDER_NOTIONAL" in lp.live_stage_block_reason()


# -- signal profile resolution ----------------------------------------------------

def test_signal_carries_paper_profile_by_default():
    from crypto_ai_system.research.active_research_signal import _resolve_signal_profile
    assert _resolve_signal_profile() == (PAPER_PROFILE_ID, PAPER_PROFILE_SHA256)


def test_signal_carries_live_profile_when_configured(monkeypatch, promoted):
    _configure_live(monkeypatch)
    from crypto_ai_system.research.active_research_signal import _resolve_signal_profile
    assert _resolve_signal_profile() == (lp.LIVE_PROFILE_ID, lp.LIVE_PROFILE_SHA256)


# -- bridge live gate --------------------------------------------------------------

def _signal(profile_id, profile_hash):
    return {
        "research_signal_id": "rs1",
        "profile_id": profile_id,
        "profile_sha256": profile_hash,
        "profile_hash": profile_hash,
        "trade_permission": {"allow_long": True, "allow_short": True, "allow_new_position": True},
    }


def _gate(execution_stage, research_signal, risk=None):
    from crypto_ai_system.strategy_factory.strategy_execution_bridge import (
        _evaluate_strategy_risk_gate,
    )

    return _evaluate_strategy_risk_gate(
        "LONG",
        execution_stage=execution_stage,
        research_signal=research_signal,
        risk=risk or {},
        market_snapshot={"last_close": 60000.0},
        open_positions=0,
        eval_id="eval1",
    )


def test_live_gate_blocked_by_default():
    gate = _gate("live", _signal(lp.LIVE_PROFILE_ID, lp.LIVE_PROFILE_SHA256))
    assert gate["approved"] is False


def test_live_gate_approves_when_fully_configured(monkeypatch, promoted):
    _configure_live(monkeypatch)
    from crypto_ai_system.strategy_factory import strategy_execution_bridge as bridge
    import crypto_ai_system.execution.live_pnl_ledger as ledger
    import crypto_ai_system.execution.live_order_final_guard as fg
    monkeypatch.setattr(ledger, "live_daily_realized_pnl_usdt", lambda **kw: 0.0)
    monkeypatch.setattr(fg, "count_today", lambda: 0)

    gate = _gate("live", _signal(lp.LIVE_PROFILE_ID, lp.LIVE_PROFILE_SHA256))
    assert gate["approved"] is True, gate.get("block_reasons") or gate
    assert gate["stage"] == "live"


def test_live_gate_blocks_on_daily_loss(monkeypatch, promoted):
    _configure_live(monkeypatch)
    import crypto_ai_system.execution.live_pnl_ledger as ledger
    import crypto_ai_system.execution.live_order_final_guard as fg
    monkeypatch.setattr(ledger, "live_daily_realized_pnl_usdt", lambda **kw: -25.0)  # limit 20
    monkeypatch.setattr(fg, "count_today", lambda: 0)

    gate = _gate("live", _signal(lp.LIVE_PROFILE_ID, lp.LIVE_PROFILE_SHA256))
    assert gate["approved"] is False


def test_live_gate_blocks_on_paper_profile_signal(monkeypatch, promoted):
    # A signal still carrying the paper profile hash must not pass the live gate.
    _configure_live(monkeypatch)
    import crypto_ai_system.execution.live_pnl_ledger as ledger
    import crypto_ai_system.execution.live_order_final_guard as fg
    monkeypatch.setattr(ledger, "live_daily_realized_pnl_usdt", lambda **kw: 0.0)
    monkeypatch.setattr(fg, "count_today", lambda: 0)

    gate = _gate("live", _signal(PAPER_PROFILE_ID, PAPER_PROFILE_SHA256))
    assert gate["approved"] is False


def test_other_stages_still_blocked(monkeypatch, promoted):
    _configure_live(monkeypatch)
    gate = _gate("signed_testnet", _signal(lp.LIVE_PROFILE_ID, lp.LIVE_PROFILE_SHA256))
    assert gate["approved"] is False
