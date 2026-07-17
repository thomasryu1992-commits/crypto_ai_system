"""The trading agent's hooks are what turn a blocked cycle into a shadow trade.
A correct tracker nobody calls records nothing, so the wiring is tested here."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.config import load_config
from crypto_ai_system.feedback import counterfactual_tracker as tracker
from crypto_ai_system.pipeline import trading_agent as ta


def _cfg(tmp_path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _snapshot():
    return {
        "last_close": 100.0,
        "atr": 2.0,
        "timeframe": "1h",
        "symbol": "BTCUSDT",
        "trend_bias": "TREND_UP",
    }


def _suppressed_decision():
    """A cycle the risk guard turned away after the permission gate had already
    rewritten the side to NONE."""
    return {
        "symbol": "BTCUSDT",
        "direction": "NONE",
        "final_decision": "BLOCK_RISK",
        "reasons": ["max_drawdown_proxy_breached"],
        "trading_signal": {"signal": "NONE"},
        "research_signal_id": "rs1",
        "decision_id": "d1",
        "profile_id": "p1",
        "pre_order_risk_gate": {
            "status": "BLOCK_DAILY_LOSS_LIMIT",
            "approved": False,
            "block_reasons": ["daily_loss_limit_gate_blocked"],
        },
    }


def _bullish_signal(tmp_path, monkeypatch):
    """Point the agent at a research signal whose bullish view a gate suppressed."""
    path = tmp_path / "research_signal.json"
    path.write_text(
        json.dumps(
            {
                "scenario": "Bullish",
                "signal_timing": "Risk-Off",
                "entry_side": "FLAT",
                "research_signal_id": "rs1",
                "profile_id": "p1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ta, "RESEARCH_SIGNAL_PATH", path)


def test_agent_shadows_a_blocked_signal(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _bullish_signal(tmp_path, monkeypatch)
    agent = ta.TradingAgent()

    plan = agent._record_counterfactual(cfg, _suppressed_decision(), _snapshot(), "cyc1")
    assert plan is not None
    assert plan["direction"] == "LONG"
    assert plan["block_reason"] == "BLOCK_DAILY_LOSS_LIMIT"


def test_agent_settle_hook_resolves_the_shadow(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _bullish_signal(tmp_path, monkeypatch)
    agent = ta.TradingAgent()
    agent._record_counterfactual(cfg, _suppressed_decision(), _snapshot(), "cyc1")

    monkeypatch.setattr(ta, "_latest_candle", lambda: {"high": 105.0, "low": 100.0})
    settled = agent._settle_counterfactuals(cfg, _snapshot() | {"last_close": 104.0})
    assert len(settled) == 1
    assert settled[0]["classification"] == tracker.MISSED_OPPORTUNITY
    assert settled[0]["result_R"] == 2.0
    assert settled[0]["regime"] == "TREND_UP"


def test_tracking_can_be_switched_off(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _bullish_signal(tmp_path, monkeypatch)
    monkeypatch.setattr(ta.settings, "COUNTERFACTUAL_TRACKING_ENABLED", False, raising=False)
    agent = ta.TradingAgent()

    assert agent._record_counterfactual(cfg, _suppressed_decision(), _snapshot(), "c1") is None
    assert agent._settle_counterfactuals(cfg, _snapshot()) == []


def test_tracker_failure_never_disturbs_execution(tmp_path, monkeypatch):
    """Counterfactual bookkeeping is observational. If it throws, the trading
    stage must carry on — a shadow-trade bug must never cost a real cycle."""
    cfg = _cfg(tmp_path)
    _bullish_signal(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("tracker exploded")

    monkeypatch.setattr(ta, "record_blocked_signal", boom)
    monkeypatch.setattr(ta, "settle_counterfactuals", boom)
    agent = ta.TradingAgent()

    assert agent._record_counterfactual(cfg, _suppressed_decision(), _snapshot(), "c1") is None
    assert agent._settle_counterfactuals(cfg, _snapshot()) == []
