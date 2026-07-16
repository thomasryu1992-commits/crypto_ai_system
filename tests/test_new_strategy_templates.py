"""The new candle-derived / higher-timeframe template families must be usable.

A template that the validator rejects, or that never matches a row, is dead
weight the factory would keep regenerating — these tests keep the new families
honest end to end: generate -> validate -> evaluate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame
from crypto_ai_system.strategy_factory.strategy_evaluator import evaluate_spec
from crypto_ai_system.strategy_factory.strategy_generator_agent import generate_batch
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.strategy_template_library import (
    DEFAULT_TEMPLATE_ORDER,
    TEMPLATES,
)
from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy

NEW_FAMILIES = (
    "macd_momentum",
    "macd_momentum_short",
    "bollinger_breakout",
    "bollinger_breakdown_short",
    "htf_trend_follow",
    "htf_trend_follow_short",
)


def _rows() -> list[dict]:
    n = 600
    ts = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    trend = np.concatenate([np.linspace(0, 4000, n // 2), np.linspace(4000, 1000, n - n // 2)])
    close = 60000 + trend + np.sin(np.arange(n) / 7) * 120
    candles = [
        {"timestamp": str(t), "open": c - 20, "high": c + 60, "low": c - 60, "close": c, "volume": 100 + (i * 7) % 60}
        for i, (t, c) in enumerate(zip(ts, close))
    ]
    return build_backtest_frame(candles).to_dict("records")


def _spec(family: str) -> StrategySpec:
    batch = generate_batch("gen_test", seed=7, count=1, templates=(TEMPLATES[family],))
    spec = batch["specs"][0]
    return spec if isinstance(spec, StrategySpec) else StrategySpec.from_dict(spec)


@pytest.mark.parametrize("family", NEW_FAMILIES)
def test_new_template_passes_the_validator(family: str) -> None:
    verdict = validate_strategy(_spec(family))
    assert verdict["approved_for_backtest"], verdict["block_reasons"]


@pytest.mark.parametrize("family", NEW_FAMILIES)
def test_new_template_actually_enters(family: str) -> None:
    """It must fire on real feature rows — a never-matching family is dead."""
    matches = sum(1 for row in _rows() if evaluate_spec(_spec(family), row).matched)
    assert matches > 0, f"{family} never matched — dead strategy family"


@pytest.mark.parametrize("family", NEW_FAMILIES)
def test_new_family_is_in_the_rotation(family: str) -> None:
    assert TEMPLATES[family] in DEFAULT_TEMPLATE_ORDER


def test_rotation_stays_direction_balanced() -> None:
    longs = sum(1 for t in DEFAULT_TEMPLATE_ORDER if t.direction.value == "long")
    shorts = sum(1 for t in DEFAULT_TEMPLATE_ORDER if t.direction.value == "short")
    assert longs == shorts
