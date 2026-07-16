"""Timeframe-aware strategy evaluation (factory retiming + runtime routing).

A spec's timeframe is part of its contract: the router must judge a 1d strategy
on the 1d frame its backtest scored, never on the pipeline's 1h row. These tests
pin the retimed template rotation, the per-timeframe row resolution in the
router, and the closed-bar discipline of the runtime row builder.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_ai_system.strategy_factory.entry_strategy_router_agent import route_entries
from crypto_ai_system.strategy_factory.runtime_feature_adapter import (
    build_runtime_feature_row_for_timeframe,
    drop_forming_bar,
)
from crypto_ai_system.strategy_factory.strategy_template_library import (
    DEFAULT_TEMPLATE_ORDER,
    TEMPLATES,
    retimed,
    templates_for_timeframe,
)


def _candles(n: int, freq: str) -> list[dict]:
    ts = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    close = 60000 + np.linspace(0, 3000, n) + np.sin(np.arange(n) / 7) * 150
    return [
        {"timestamp": str(t), "open": c - 20, "high": c + 60, "low": c - 60, "close": c, "volume": 100.0}
        for t, c in zip(ts, close)
    ]


# --- template retiming --------------------------------------------------------

def test_retimed_changes_only_the_timeframe() -> None:
    base = TEMPLATES["breakout"]
    daily = retimed(base, "1d")
    assert daily.timeframe == "1d"
    assert (daily.family, daily.direction, daily.param_space) == (
        base.family, base.direction, base.param_space,
    )


@pytest.mark.parametrize("tf", ["4h", "1d"])
def test_htf_families_are_dropped_at_or_above_their_own_legs(tf: str) -> None:
    families = {t.family for t in templates_for_timeframe(tf)}
    assert not any(f.startswith("htf_") for f in families), (
        "an htf_* spec on a >=4h base can never fire; it must not be generated"
    )


def test_lower_timeframes_keep_the_full_rotation() -> None:
    assert len(templates_for_timeframe("15m")) == len(DEFAULT_TEMPLATE_ORDER)
    assert all(t.timeframe == "15m" for t in templates_for_timeframe("15m"))


def test_widened_target_space_still_validates() -> None:
    """The 8.0 target ceiling must stay inside the validator's allowed range."""
    from crypto_ai_system.strategy_factory.strategy_generator_agent import generate_batch
    from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
    from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy

    template = retimed(TEMPLATES["breakout"], "1d")
    for seed in range(5):
        batch = generate_batch("gen_t", seed=seed, count=1, templates=(template,))
        spec = batch["specs"][0]
        spec = spec if isinstance(spec, StrategySpec) else StrategySpec.from_dict(spec)
        verdict = validate_strategy(spec)
        assert verdict["approved_for_backtest"], verdict["block_reasons"]


# --- router: per-timeframe row resolution -------------------------------------

def _pool_entry(strategy_id: str, timeframe: str) -> dict:
    from crypto_ai_system.strategy_factory.strategy_generator_agent import generate_batch

    batch = generate_batch(
        "gen_r", seed=7, count=1, templates=(retimed(TEMPLATES["breakout"], timeframe),)
    )
    spec = batch["specs"][0]
    spec_dict = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec)
    return {
        "strategy_id": strategy_id,
        "strategy_rule_hash": spec_dict.get("strategy_rule_hash", "h"),
        "status": "PAPER_ACTIVE",
        "champion_score": 0.5,
        "strategy_spec": spec_dict,
    }


_MATCH_ROW = {"close": 110.0, "ma20": 100.0, "ma50": 90.0, "adx": 40.0}


def test_router_resolves_each_spec_to_its_timeframe_row() -> None:
    pool = {"active_strategies": [_pool_entry("S1", "1h"), _pool_entry("S2", "1d")]}
    result = route_entries(
        pool, {}, feature_rows={"1h": _MATCH_ROW, "1d": {"close": 1.0, "ma20": 100.0, "ma50": 90.0, "adx": 40.0}}
    )
    by_id = {e["strategy_id"]: e for e in result["evaluations"]}
    assert by_id["S1"]["matched"] is True and by_id["S1"]["timeframe"] == "1h"
    assert by_id["S2"]["matched"] is False, "the 1d spec must be judged on the 1d row"


def test_router_marks_specs_without_a_row_unevaluable() -> None:
    pool = {"active_strategies": [_pool_entry("S1", "1d")]}
    result = route_entries(pool, {}, feature_rows={"1h": _MATCH_ROW})
    (evaluation,) = result["evaluations"]
    assert evaluation["matched"] is False
    assert "1d" in evaluation["unevaluable"]
    assert result["status"] == "NO_ENTRY", "a missing row must fail closed, not match"


def test_router_without_feature_rows_keeps_single_row_behavior() -> None:
    pool = {"active_strategies": [_pool_entry("S1", "1h")]}
    result = route_entries(pool, _MATCH_ROW)
    assert result["status"] == "ENTRY_CANDIDATE"


# --- closed-bar discipline ------------------------------------------------------

def test_drop_forming_bar_drops_only_the_unfinished_last_bar() -> None:
    candles = _candles(10, "1D")
    now = str(pd.to_datetime(candles[-1]["timestamp"]) + pd.Timedelta(hours=5))
    kept = drop_forming_bar(candles, "1d", now=now)
    assert len(kept) == 9, "the 5h-old daily bar is still forming and must be dropped"

    now_closed = str(pd.to_datetime(candles[-1]["timestamp"]) + pd.Timedelta(days=1, minutes=1))
    assert len(drop_forming_bar(candles, "1d", now=now_closed)) == 10


def test_drop_forming_bar_keeps_unknown_timeframes_intact() -> None:
    candles = _candles(5, "1D")
    assert len(drop_forming_bar(candles, "3w")) == 5


def test_runtime_row_for_base_timeframe_uses_pipeline_candles() -> None:
    row = build_runtime_feature_row_for_timeframe(
        "1h", _candles(300, "1h"), base_timeframe="1h",
        history_loader=lambda tf, bars: pytest.fail("must not load history for the base timeframe"),
    )
    assert row and row["close"] > 0


def test_runtime_row_for_other_timeframe_uses_injected_history() -> None:
    daily = _candles(300, "1D")
    row = build_runtime_feature_row_for_timeframe(
        "1d", _candles(50, "1h"), base_timeframe="1h",
        history_loader=lambda tf, bars: daily,
        now=str(pd.to_datetime(daily[-1]["timestamp"]) + pd.Timedelta(days=2)),
    )
    assert row["timestamp"] == daily[-1]["timestamp"]


def test_runtime_row_drops_the_forming_bar_from_history() -> None:
    daily = _candles(300, "1D")
    row = build_runtime_feature_row_for_timeframe(
        "1d", [], base_timeframe="1h",
        history_loader=lambda tf, bars: daily,
        now=str(pd.to_datetime(daily[-1]["timestamp"]) + pd.Timedelta(hours=3)),
    )
    assert row["timestamp"] == daily[-2]["timestamp"], (
        "a half-formed daily bar must never be evaluated"
    )


def test_runtime_row_fails_closed_when_history_loading_raises() -> None:
    def boom(tf: str, bars: int):
        raise RuntimeError("venue down")

    row = build_runtime_feature_row_for_timeframe(
        "1d", [], base_timeframe="1h", history_loader=boom
    )
    assert row == {}
