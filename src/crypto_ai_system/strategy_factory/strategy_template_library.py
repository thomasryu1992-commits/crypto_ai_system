"""Phase S2: the allowed strategy templates (multi-regime, long + short).

Generation is *template + parameter*, never free code. Each template is a family
of strategies sharing an entry shape; a concrete strategy is that shape with
parameters filled in from a bounded space. The library spans the three regimes
the directive targets — trend, breakout/breakdown, and range — in both
directions, so the factory can produce a strategy suited to whatever the market
is doing. Which ones actually qualify is decided by the backtest on real history:
in a long uptrend the long-trend families win and the shorts don't, and the pool
adapts as conditions change.

Every template references only ``feature_store`` columns that carry real values at
runtime — candle-derived indicators (MACD, Bollinger, ROC, volume z-score) and the
resampled higher-timeframe trend, never a feed the lean runtime does not supply.
So a mutated instance is evaluable and lands inside the S3 validator's ranges by
design — the validator is still the gate.
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
    # Uptrend, trend has strength, momentum pulled back (not overbought).
    return [
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
        {"feature": "rsi", "comparison": "<=", "value": p["rsi_max"]},
    ]


def _trend_pullback_short_entry(p: dict) -> list[dict]:
    # Downtrend, trend has strength, momentum bounced (not oversold) — short it.
    return [
        {"feature": "ma20", "comparison": "<", "value_from": "ma50"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
        {"feature": "rsi", "comparison": ">=", "value": p["rsi_min"]},
    ]


def _breakout_entry(p: dict) -> list[dict]:
    # Price above the fast MA in an uptrend with trend strength (price-based).
    return [
        {"feature": "close", "comparison": ">", "value_from": "ma20"},
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
    ]


def _breakdown_short_entry(p: dict) -> list[dict]:
    # Price below the fast MA in a downtrend with trend strength.
    return [
        {"feature": "close", "comparison": "<", "value_from": "ma20"},
        {"feature": "ma20", "comparison": "<", "value_from": "ma50"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
    ]


def _mean_reversion_long_entry(p: dict) -> list[dict]:
    # Oversold momentum inside a ranging regime — buy the dip.
    return [
        {"feature": "rsi", "comparison": "<=", "value": p["rsi_max"]},
        {"feature": "market_regime", "comparison": "==", "value": "RANGE"},
    ]


def _mean_reversion_short_entry(p: dict) -> list[dict]:
    # Overbought momentum inside a ranging regime — sell the rip.
    return [
        {"feature": "rsi", "comparison": ">=", "value": p["rsi_min"]},
        {"feature": "market_regime", "comparison": "==", "value": "RANGE"},
    ]


def _macd_momentum_entry(p: dict) -> list[dict]:
    # MACD above its signal with a positive, strengthening histogram in an uptrend.
    return [
        {"feature": "macd_hist", "comparison": ">", "value": 0.0},
        {"feature": "macd", "comparison": ">", "value_from": "macd_signal"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
    ]


def _macd_momentum_short_entry(p: dict) -> list[dict]:
    return [
        {"feature": "macd_hist", "comparison": "<", "value": 0.0},
        {"feature": "macd", "comparison": "<", "value_from": "macd_signal"},
        {"feature": "adx", "comparison": ">=", "value": p["adx_min"]},
    ]


def _bollinger_breakout_entry(p: dict) -> list[dict]:
    # Price pushing the upper band out of a (relatively) tight band — expansion.
    return [
        {"feature": "bb_percent_b", "comparison": ">=", "value": p["percent_b_min"]},
        {"feature": "volume_zscore", "comparison": ">=", "value": p["volume_z_min"]},
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
    ]


def _bollinger_breakdown_short_entry(p: dict) -> list[dict]:
    return [
        {"feature": "bb_percent_b", "comparison": "<=", "value": p["percent_b_max"]},
        {"feature": "volume_zscore", "comparison": ">=", "value": p["volume_z_min"]},
        {"feature": "ma20", "comparison": "<", "value_from": "ma50"},
    ]


def _htf_trend_follow_entry(p: dict) -> list[dict]:
    # Base-timeframe pullback taken only when 4h and 1d agree upward.
    return [
        {"feature": "htf_alignment_score", "comparison": ">=", "value": p["alignment_min"]},
        {"feature": "htf_1d_trend", "comparison": "==", "value": "UP"},
        {"feature": "rsi", "comparison": "<=", "value": p["rsi_max"]},
    ]


def _htf_trend_follow_short_entry(p: dict) -> list[dict]:
    return [
        {"feature": "htf_alignment_score", "comparison": "<=", "value": p["alignment_max"]},
        {"feature": "htf_1d_trend", "comparison": "==", "value": "DOWN"},
        {"feature": "rsi", "comparison": ">=", "value": p["rsi_min"]},
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

TREND_PULLBACK_SHORT = StrategyTemplate(
    family="trend_pullback_short",
    direction=Direction.SHORT,
    timeframe="1h",
    param_space={"adx_min": ParamSpec(15.0, 30.0), "rsi_min": ParamSpec(35.0, 55.0), **_EXIT_PARAMS},
    base_params={"adx_min": 22.0, "rsi_min": 45.0, **_EXIT_BASE},
    entry_builder=_trend_pullback_short_entry,
)

BREAKOUT = StrategyTemplate(
    family="breakout",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={"adx_min": ParamSpec(18.0, 35.0), **_EXIT_PARAMS},
    base_params={"adx_min": 25.0, **_EXIT_BASE},
    entry_builder=_breakout_entry,
)

BREAKDOWN_SHORT = StrategyTemplate(
    family="breakdown_short",
    direction=Direction.SHORT,
    timeframe="1h",
    param_space={"adx_min": ParamSpec(18.0, 35.0), **_EXIT_PARAMS},
    base_params={"adx_min": 25.0, **_EXIT_BASE},
    entry_builder=_breakdown_short_entry,
)

MEAN_REVERSION = StrategyTemplate(
    family="mean_reversion",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={"rsi_max": ParamSpec(20.0, 40.0), **_EXIT_PARAMS},
    base_params={"rsi_max": 30.0, **_EXIT_BASE},
    entry_builder=_mean_reversion_long_entry,
)

MEAN_REVERSION_SHORT = StrategyTemplate(
    family="mean_reversion_short",
    direction=Direction.SHORT,
    timeframe="1h",
    param_space={"rsi_min": ParamSpec(60.0, 80.0), **_EXIT_PARAMS},
    base_params={"rsi_min": 70.0, **_EXIT_BASE},
    entry_builder=_mean_reversion_short_entry,
)

MACD_MOMENTUM = StrategyTemplate(
    family="macd_momentum",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={"adx_min": ParamSpec(15.0, 30.0), **_EXIT_PARAMS},
    base_params={"adx_min": 20.0, **_EXIT_BASE},
    entry_builder=_macd_momentum_entry,
)

MACD_MOMENTUM_SHORT = StrategyTemplate(
    family="macd_momentum_short",
    direction=Direction.SHORT,
    timeframe="1h",
    param_space={"adx_min": ParamSpec(15.0, 30.0), **_EXIT_PARAMS},
    base_params={"adx_min": 20.0, **_EXIT_BASE},
    entry_builder=_macd_momentum_short_entry,
)

BOLLINGER_BREAKOUT = StrategyTemplate(
    family="bollinger_breakout",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={
        "percent_b_min": ParamSpec(0.9, 1.1),
        "volume_z_min": ParamSpec(0.5, 2.0),
        **_EXIT_PARAMS,
    },
    base_params={"percent_b_min": 1.0, "volume_z_min": 1.0, **_EXIT_BASE},
    entry_builder=_bollinger_breakout_entry,
)

BOLLINGER_BREAKDOWN_SHORT = StrategyTemplate(
    family="bollinger_breakdown_short",
    direction=Direction.SHORT,
    timeframe="1h",
    param_space={
        "percent_b_max": ParamSpec(-0.1, 0.1),
        "volume_z_min": ParamSpec(0.5, 2.0),
        **_EXIT_PARAMS,
    },
    base_params={"percent_b_max": 0.0, "volume_z_min": 1.0, **_EXIT_BASE},
    entry_builder=_bollinger_breakdown_short_entry,
)

HTF_TREND_FOLLOW = StrategyTemplate(
    family="htf_trend_follow",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={"alignment_min": ParamSpec(0.5, 1.0), "rsi_max": ParamSpec(45.0, 65.0), **_EXIT_PARAMS},
    base_params={"alignment_min": 1.0, "rsi_max": 55.0, **_EXIT_BASE},
    entry_builder=_htf_trend_follow_entry,
)

HTF_TREND_FOLLOW_SHORT = StrategyTemplate(
    family="htf_trend_follow_short",
    direction=Direction.SHORT,
    timeframe="1h",
    param_space={"alignment_max": ParamSpec(-1.0, -0.5), "rsi_min": ParamSpec(35.0, 55.0), **_EXIT_PARAMS},
    base_params={"alignment_max": -1.0, "rsi_min": 45.0, **_EXIT_BASE},
    entry_builder=_htf_trend_follow_short_entry,
)

TEMPLATES: dict[str, StrategyTemplate] = {
    t.family: t for t in (
        TREND_PULLBACK, TREND_PULLBACK_SHORT, BREAKOUT, BREAKDOWN_SHORT,
        MEAN_REVERSION, MEAN_REVERSION_SHORT,
        MACD_MOMENTUM, MACD_MOMENTUM_SHORT,
        BOLLINGER_BREAKOUT, BOLLINGER_BREAKDOWN_SHORT,
        HTF_TREND_FOLLOW, HTF_TREND_FOLLOW_SHORT,
    )
}

# Rotation order pairs each long family with its short mirror, so a batch spans
# directions and regimes.
DEFAULT_TEMPLATE_ORDER = (
    TREND_PULLBACK, TREND_PULLBACK_SHORT, BREAKOUT, BREAKDOWN_SHORT,
    MEAN_REVERSION, MEAN_REVERSION_SHORT,
    MACD_MOMENTUM, MACD_MOMENTUM_SHORT,
    BOLLINGER_BREAKOUT, BOLLINGER_BREAKDOWN_SHORT,
    HTF_TREND_FOLLOW, HTF_TREND_FOLLOW_SHORT,
)
