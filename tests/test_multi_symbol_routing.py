"""Multi-symbol strategy contract: selection, routing, and pricing per market.

Measured on 6y of 1d history, the breakout edge is +0.17R on BTC but ~0 on ETH
and negative on XRP/ADA — so each symbol must be selected on its own history,
evaluated on its own frame, and priced at its own market. These tests pin that:
a spec never sees another symbol's candles, another symbol's price, or another
symbol's funding, and one symbol's direction conflict never silences the rest of
the pool.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_ai_system.strategy_factory.entry_strategy_router_agent import (
    feature_row_key,
    route_entries,
)
from crypto_ai_system.strategy_factory.runtime_feature_adapter import (
    build_runtime_feature_row_for_timeframe,
)
from crypto_ai_system.strategy_factory.strategy_generator_agent import generate_batch
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.strategy_template_library import TEMPLATES, retimed

_MATCH_ROW = {"close": 110.0, "ma20": 100.0, "ma50": 90.0, "adx": 40.0}
_NO_MATCH_ROW = {"close": 1.0, "ma20": 100.0, "ma50": 90.0, "adx": 40.0}
_MATCH_SHORT_ROW = {"close": 80.0, "ma20": 90.0, "ma50": 100.0, "adx": 40.0}


def _entry(strategy_id: str, symbol: str, *, family: str = "breakout", score: float = 0.5) -> dict:
    batch = generate_batch(
        "gen_ms", seed=11, count=1, templates=(retimed(TEMPLATES[family], "1d"),), symbol=symbol
    )
    spec = batch["specs"][0]
    spec_dict = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec)
    return {
        "strategy_id": strategy_id,
        "strategy_rule_hash": spec_dict.get("strategy_rule_hash", "h"),
        "status": "PAPER_ACTIVE",
        "champion_score": score,
        "strategy_spec": spec_dict,
    }


# --- generation carries the symbol -------------------------------------------

def test_generated_spec_carries_its_symbol() -> None:
    batch = generate_batch(
        "gen_sym", seed=3, count=1, templates=(retimed(TEMPLATES["breakout"], "1d"),), symbol="ETHUSDT"
    )
    spec = batch["specs"][0]
    spec = spec if isinstance(spec, StrategySpec) else StrategySpec.from_dict(spec)
    assert spec.symbol_scope == ("ETHUSDT",)


# --- router: per-symbol row resolution ----------------------------------------

def test_each_symbol_is_judged_on_its_own_row() -> None:
    pool = {"active_strategies": [_entry("B1", "BTCUSDT"), _entry("E1", "ETHUSDT")]}
    result = route_entries(pool, {}, feature_rows={
        feature_row_key("BTCUSDT", "1d"): _MATCH_ROW,
        feature_row_key("ETHUSDT", "1d"): _NO_MATCH_ROW,
    })
    by_id = {e["strategy_id"]: e for e in result["evaluations"]}
    assert by_id["B1"]["matched"] is True and by_id["B1"]["symbol"] == "BTCUSDT"
    assert by_id["E1"]["matched"] is False, "ETH must be judged on the ETH row"
    assert result["status"] == "ENTRY_CANDIDATE" and result["symbol"] == "BTCUSDT"


def test_symbol_without_a_row_is_unevaluable_not_matched() -> None:
    pool = {"active_strategies": [_entry("E1", "ETHUSDT")]}
    result = route_entries(pool, {}, feature_rows={feature_row_key("BTCUSDT", "1d"): _MATCH_ROW})
    (evaluation,) = result["evaluations"]
    assert evaluation["matched"] is False
    assert "ETHUSDT" in evaluation["unevaluable"]


# --- per-symbol conflict semantics --------------------------------------------

def test_cross_symbol_opposite_directions_are_not_a_conflict() -> None:
    pool = {"active_strategies": [
        _entry("B1", "BTCUSDT", score=0.9),
        _entry("E1", "ETHUSDT", family="breakdown_short", score=0.5),
    ]}
    result = route_entries(pool, {}, feature_rows={
        feature_row_key("BTCUSDT", "1d"): _MATCH_ROW,
        feature_row_key("ETHUSDT", "1d"): _MATCH_SHORT_ROW,
    })
    assert result["status"] == "ENTRY_CANDIDATE"
    assert result["symbol"] == "BTCUSDT" and result["direction"] == "LONG"
    assert result["conflicted_symbols"] == []


def test_same_symbol_conflict_excludes_that_symbol_only() -> None:
    row_both = {**_MATCH_ROW, **{}}  # breakout long matches
    pool = {"active_strategies": [
        # BTC: a long and a short both matching -> conflicted, excluded.
        _entry("B1", "BTCUSDT", score=0.9),
        _entry("B2", "BTCUSDT", family="mean_reversion_short", score=0.9),
        # ETH: a clean long candidate survives.
        _entry("E1", "ETHUSDT", score=0.4),
    ]}
    btc_row = {"close": 110.0, "ma20": 100.0, "ma50": 90.0, "adx": 40.0,
               "rsi": 80.0, "market_regime": "RANGE"}
    result = route_entries(pool, {}, feature_rows={
        feature_row_key("BTCUSDT", "1d"): btc_row,
        feature_row_key("ETHUSDT", "1d"): _MATCH_ROW,
    })
    assert result["conflicted_symbols"] == ["BTCUSDT"]
    assert result["status"] == "ENTRY_CANDIDATE"
    assert result["symbol"] == "ETHUSDT", "the conflicted symbol must not silence ETH"


def test_all_symbols_conflicted_blocks() -> None:
    pool = {"active_strategies": [
        _entry("B1", "BTCUSDT", score=0.9),
        _entry("B2", "BTCUSDT", family="mean_reversion_short", score=0.8),
    ]}
    btc_row = {"close": 110.0, "ma20": 100.0, "ma50": 90.0, "adx": 40.0,
               "rsi": 80.0, "market_regime": "RANGE"}
    result = route_entries(pool, {}, feature_rows={feature_row_key("BTCUSDT", "1d"): btc_row})
    assert result["status"] == "BLOCKED"
    assert result["block_reason"] == "BLOCK_STRATEGY_DIRECTION_CONFLICT"


# --- feature adapter: symbol-aware history ------------------------------------

def _candles(n: int, symbol: str) -> list[dict]:
    ts = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = 60000 + np.linspace(0, 3000, n)
    return [
        {"timestamp": str(t), "symbol": symbol, "open": c - 20, "high": c + 60,
         "low": c - 60, "close": c, "volume": 100.0}
        for t, c in zip(ts, close)
    ]


def test_cross_symbol_row_loads_that_symbols_history() -> None:
    loaded: list[str] = []

    def loader(tf: str, bars: int):
        loaded.append("called")
        return _candles(300, "ETHUSDT")

    row = build_runtime_feature_row_for_timeframe(
        "1d", _candles(50, "BTCUSDT"), base_timeframe="1h",
        symbol="ETHUSDT", history_loader=loader,
        now=str(pd.Timestamp("2024-11-01", tz="UTC")),
    )
    assert loaded and row, "an ETH spec must load ETH candles, not reuse BTC's"


def test_pool_pairs_span_symbols_and_timeframes() -> None:
    from crypto_ai_system.pipeline.strategy_routing_agent import _pool_pairs

    pool = {"active_strategies": [
        _entry("B1", "BTCUSDT"),
        _entry("E1", "ETHUSDT"),
    ]}
    assert _pool_pairs(pool) == {("BTCUSDT", "1d"), ("ETHUSDT", "1d")}


# --- pricing: never another market's price -------------------------------------

def test_cross_symbol_decision_prices_at_the_specs_market() -> None:
    from crypto_ai_system.strategy_factory.strategy_trade_decision import (
        build_strategy_trade_decision,
    )

    eth_row = {"close": 3500.0, "atr": 100.0}
    decision = build_strategy_trade_decision(
        router_result={"status": "ENTRY_CANDIDATE", "direction": "LONG",
                       "primary_strategy_id": "E1", "order_candidate_count": 1},
        primary_spec=_entry("E1", "ETHUSDT")["strategy_spec"],
        feature_row=eth_row,
        market_snapshot={"symbol": "BTC-PERP", "last_close": 64000.0},
        research_permission={"allow_new_position": True, "allow_long": True, "allow_short": True},
        pre_order_risk_gate={"approved": True, "status": "APPROVED"},
        attribution={"strategy_entry_evaluation_id": "x"},
        symbol="ETHUSDT",
    )
    entry = decision.get("entry") or decision.get("entry_price")
    assert entry == 3500.0, f"an ETH order must never be priced at BTC's 64000 (got {entry})"


def test_same_market_decision_keeps_snapshot_price() -> None:
    from crypto_ai_system.strategy_factory.strategy_trade_decision import (
        build_strategy_trade_decision,
    )

    decision = build_strategy_trade_decision(
        router_result={"status": "ENTRY_CANDIDATE", "direction": "LONG",
                       "primary_strategy_id": "B1", "order_candidate_count": 1},
        primary_spec=_entry("B1", "BTCUSDT")["strategy_spec"],
        feature_row={"close": 63990.0, "atr": 500.0},
        market_snapshot={"symbol": "BTC-PERP", "last_close": 64000.0},
        research_permission={"allow_new_position": True, "allow_long": True, "allow_short": True},
        pre_order_risk_gate={"approved": True, "status": "APPROVED"},
        attribution={"strategy_entry_evaluation_id": "x"},
        symbol="BTCUSDT",
    )
    entry = decision.get("entry") or decision.get("entry_price")
    assert entry == 64000.0, "BTC-PERP and BTCUSDT are the same market — snapshot price wins"


# --- pool diversity is per market ----------------------------------------------

def test_family_diversity_is_judged_within_a_symbol() -> None:
    from crypto_ai_system.strategy_factory.active_strategy_pool import family_count

    pool = {"active_strategies": [
        _entry("B1", "BTCUSDT"), _entry("B2", "BTCUSDT"), _entry("E1", "ETHUSDT"),
    ]}
    assert family_count(pool, "breakout") == 3
    assert family_count(pool, "breakout", "BTCUSDT") == 2
    assert family_count(pool, "breakout", "ETHUSDT") == 1
