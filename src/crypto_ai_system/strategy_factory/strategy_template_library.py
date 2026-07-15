"""Phase S2: the allowed strategy templates.

Generation is *template + parameter*, never free code (the directive forbids
runtime code generation at this stage). Each template is a family of strategies
sharing an entry shape; a concrete strategy is that shape with parameters filled
in from a bounded space. Every template references only real ``feature_store``
columns and produces exit rules with a stop, so a mutated instance lands inside
the S3 validator's ranges by design — the validator is still the gate.

Templates here are long-only for the first iteration; symmetric long/short
templates are a later addition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from crypto_ai_system.strategy_factory.strategy_spec import Direction


@dataclass(frozen=True)
class ParamSpec:
    """A tunable parameter and the closed interval it may take."""

    lo: float
    hi: float
    integer: bool = False


@dataclass(frozen=True)
class StrategyTemplate:
    family: str
    direction: Direction
    timeframe: str
    param_space: dict[str, ParamSpec]
    base_params: dict[str, float]
    # (params) -> list of entry condition dicts
    entry_builder: Callable[[dict], list[dict]]

    def build_entry_conditions(self, params: dict) -> list[dict]:
        return self.entry_builder(params)

    def build_exit_rules(self, params: dict) -> dict:
        return {
            "stop_model": "atr",
            "stop_atr": params["stop_atr"],
            "target_atr": params["target_atr"],
            "max_holding_bars": int(params["max_holding_bars"]),
        }


# -- entry builders (each references only real feature_store columns) ---------

def _trend_pullback_entry(p: dict) -> list[dict]:
    # Uptrend (fast MA over slow MA), trend has strength, momentum not overbought.
    return [
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
        {"feature": "rsi", "comparison": "<=", "value": p["rsi_max"]},
    ]


def _breakout_entry(p: dict) -> list[dict]:
    # Price above the fast MA, trending, with rising open interest confirming.
    return [
        {"feature": "close", "comparison": ">", "value_from": "ma20"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
        {"feature": "oi_change_pct", "comparison": ">=", "value": p["oi_min"]},
    ]


def _mean_reversion_entry(p: dict) -> list[dict]:
    # Oversold momentum inside a ranging regime (categorical condition).
    return [
        {"feature": "rsi", "comparison": "<=", "value": p["rsi_max"]},
        {"feature": "market_regime", "comparison": "==", "value": "RANGE"},
    ]


_EXIT_PARAMS = {
    "stop_atr": ParamSpec(0.8, 2.0),
    "target_atr": ParamSpec(1.6, 4.0),
    "max_holding_bars": ParamSpec(12, 48, integer=True),
}
_EXIT_BASE = {"stop_atr": 1.2, "target_atr": 2.4, "max_holding_bars": 24}


TREND_PULLBACK = StrategyTemplate(
    family="trend_pullback",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={"adx_min": ParamSpec(15.0, 30.0), "rsi_max": ParamSpec(45.0, 65.0), **_EXIT_PARAMS},
    base_params={"adx_min": 22.0, "rsi_max": 55.0, **_EXIT_BASE},
    entry_builder=_trend_pullback_entry,
)

BREAKOUT = StrategyTemplate(
    family="breakout",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={"adx_min": ParamSpec(18.0, 35.0), "oi_min": ParamSpec(0.1, 1.0), **_EXIT_PARAMS},
    base_params={"adx_min": 25.0, "oi_min": 0.3, **_EXIT_BASE},
    entry_builder=_breakout_entry,
)

MEAN_REVERSION = StrategyTemplate(
    family="mean_reversion",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={"rsi_max": ParamSpec(20.0, 40.0), **_EXIT_PARAMS},
    base_params={"rsi_max": 30.0, **_EXIT_BASE},
    entry_builder=_mean_reversion_entry,
)

TEMPLATES: dict[str, StrategyTemplate] = {
    TREND_PULLBACK.family: TREND_PULLBACK,
    BREAKOUT.family: BREAKOUT,
    MEAN_REVERSION.family: MEAN_REVERSION,
}

DEFAULT_TEMPLATE_ORDER = (TREND_PULLBACK, BREAKOUT, MEAN_REVERSION)
