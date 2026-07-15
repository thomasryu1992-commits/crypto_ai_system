"""Live wiring (shadow): runtime feature adapter + StrategyRoutingAgent."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.config import load_config
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_runtime_feature_row
from crypto_ai_system.pipeline.strategy_routing_agent import (
    STATUS_DISABLED,
    STATUS_NO_ACTIVE_STRATEGIES,
    STATUS_NO_FEATURE_ROW,
    StrategyRoutingAgent,
    evaluate_live_routing,
)
from crypto_ai_system.pipeline.contracts import CycleEnvelope, PipelineContext, StageStatus

NOW = "2026-07-16T00:00:00Z"


def _uptrend_candles(n=120):
    # Rising overall (ma20 > ma50, regime up) but with real up/down bars so
    # indicators like RSI are well-defined (a monotonic series degenerates them).
    rows = []
    base = 60000.0
    for i in range(n):
        base *= 1.002
        wobble = 1.0 + (0.006 if i % 2 == 0 else -0.004)  # alternating gains/losses
        close = base * wobble
        rows.append({"timestamp": f"2026-07-10 {i:02d}:00:00+00:00",
                     "open": close * 0.999, "high": close * 1.004,
                     "low": close * 0.996, "close": close, "volume": 1000 + i})
    return rows


def _spec(strategy_id, conditions):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1", "strategy_id": strategy_id, "strategy_version": "1.0",
        "generation_id": "GEN-001", "strategy_family": "trend_pullback", "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"], "timeframe": "1h", "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": conditions},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 24},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    }).to_dict()


# -- runtime feature adapter --------------------------------------------------

def test_feature_adapter_builds_full_row_from_candles():
    row = build_runtime_feature_row(_uptrend_candles(), cfg=load_config("."))
    for key in ("ma20", "ma50", "ema20", "rsi", "adx", "atr", "market_regime", "price_distance_ma20"):
        assert key in row, key
    assert row["ma20"] is not None and row["rsi"] is not None


def test_feature_adapter_too_few_candles_empty():
    assert build_runtime_feature_row([], cfg=load_config(".")) == {}
    assert build_runtime_feature_row(_uptrend_candles(1), cfg=load_config(".")) == {}


def test_feature_adapter_missing_columns_empty():
    bad = [{"close": 1}, {"close": 2}]
    assert build_runtime_feature_row(bad, cfg=load_config(".")) == {}


# -- evaluate_live_routing (pure core) ----------------------------------------

def test_routing_no_active_strategies():
    result = evaluate_live_routing(empty_pool(), _uptrend_candles(), now=NOW)
    assert result["status"] == STATUS_NO_ACTIVE_STRATEGIES
    assert result["order_candidate_count"] == 0


def test_routing_no_candles():
    pool, _ = add_champion(empty_pool(), _spec("S001", [{"feature": "rsi", "comparison": "<=", "value": 100}]), 0.7, now=NOW)
    result = evaluate_live_routing(pool, [], now=NOW)
    assert result["status"] == STATUS_NO_FEATURE_ROW


def test_routing_matches_active_strategy_on_live_features():
    # ma20 > ma50 holds on a sustained uptrend -> entry candidate.
    pool, _ = add_champion(empty_pool(), _spec("S001", [{"feature": "ma20", "comparison": ">", "value_from": "ma50"}]), 0.7, now=NOW)
    result = evaluate_live_routing(pool, _uptrend_candles(), now=NOW)
    assert result["status"] == "ENTRY_CANDIDATE"
    assert result["order_candidate_count"] == 1
    assert result["primary_strategy_id"] == "S001"


# -- agent flag gating --------------------------------------------------------

def _ctx():
    return PipelineContext(cycle=CycleEnvelope(cycle_id="cycle_x", started_at_utc=NOW, stage="paper"))


def test_agent_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", False, raising=False)
    result = StrategyRoutingAgent().run(_ctx())
    assert result.status is StageStatus.OK
    assert result.outputs["strategy_routing_enabled"] is False
    assert result.outputs["strategy_routing"]["status"] == STATUS_DISABLED


def test_agent_never_halts_even_on_error(monkeypatch):
    monkeypatch.setattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", True, raising=False)
    # Point the pool path at something that makes read fail internally; the agent
    # must still not halt the pipeline (fatal_on_error is False).
    result = StrategyRoutingAgent().run(_ctx())
    assert result.halts is False


def test_agent_is_non_fatal():
    assert StrategyRoutingAgent.fatal_on_error is False


# -- orchestrator wiring ------------------------------------------------------

def test_pipeline_excludes_routing_agent_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", False, raising=False)
    from crypto_ai_system.pipeline.orchestrator import Pipeline
    stages = [a.name for a in Pipeline().pre_trade]
    assert "strategy_routing" not in stages
    assert stages == ["data", "research", "validation"]


def test_pipeline_includes_routing_agent_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", True, raising=False)
    from crypto_ai_system.pipeline.orchestrator import Pipeline
    stages = [a.name for a in Pipeline().pre_trade]
    assert stages == ["data", "research", "validation", "strategy_routing"]
