"""The hot-path PreOrderRiskGate must judge against the same loss limits as the
cold-path risk_guard (config.settings), not its own hardcoded defaults."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bridge.research_trading_bridge as bridge


def _gate(monkeypatch, risk: dict) -> dict:
    monkeypatch.setattr(bridge, "persist_risk_gate_record", lambda *a, **k: None)
    return bridge._evaluate_pre_order_gate(
        "paper",
        research={},
        research_signal={},
        risk=risk,
        market_snapshot={"last_close": 60000.0},
        open_positions=0,
    )


def test_daily_loss_limit_comes_from_settings(monkeypatch):
    # Tighter than the gate's hardcoded default (-2.0): a -1.0R day must fail
    # the check, proving the settings value reached the gate.
    monkeypatch.setattr(bridge, "DAILY_MAX_LOSS_R", -0.5)
    gate = _gate(monkeypatch, {"daily_pnl_r": -1.0})
    assert gate["policy_checks"]["daily_loss_limit_ok"] is False


def test_daily_loss_within_settings_limit_passes(monkeypatch):
    monkeypatch.setattr(bridge, "DAILY_MAX_LOSS_R", -2.0)
    gate = _gate(monkeypatch, {"daily_pnl_r": -1.0})
    assert gate["policy_checks"]["daily_loss_limit_ok"] is True


def test_consecutive_loss_limit_comes_from_settings(monkeypatch):
    # Tighter than the gate's hardcoded default (3): 2 straight losses must fail.
    monkeypatch.setattr(bridge, "MAX_CONSECUTIVE_LOSSES", 1)
    gate = _gate(monkeypatch, {"consecutive_losses": 2})
    assert gate["policy_checks"]["consecutive_loss_limit_ok"] is False
