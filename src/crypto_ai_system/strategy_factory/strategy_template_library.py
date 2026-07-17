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

from dataclasses import dataclass, replace
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


def _funding_fade_short_entry(p: dict) -> list[dict]:
    # Crowded longs: funding far above its rolling norm while momentum is
    # stretched — fade the crowd short.
    return [
        {"feature": "funding_zscore", "comparison": ">=", "value": p["funding_z_min"]},
        {"feature": "rsi", "comparison": ">=", "value": p["rsi_min"]},
    ]


def _funding_fade_long_entry(p: dict) -> list[dict]:
    # Crowded shorts: funding far below its rolling norm while momentum is
    # washed out — fade the crowd long.
    return [
        {"feature": "funding_zscore", "comparison": "<=", "value": p["funding_z_max"]},
        {"feature": "rsi", "comparison": "<=", "value": p["rsi_max"]},
    ]


# target_atr reaches to 8.0: the 1d sweep was monotonically better all the way to
# the old 4.0 ceiling (+0.395R at 4.0 vs +0.198R at 2.4), i.e. the cap was cutting
# winners short. The validator's TARGET_ATR_RANGE (10.0) still bounds it.
_EXIT_PARAMS = {
    "stop_atr": ParamSpec(0.8, 2.0),
    "target_atr": ParamSpec(1.6, 8.0),
    "max_holding_bars": ParamSpec(12, 48, integer=True),
}
_EXIT_BASE = {"stop_atr": 1.2, "target_atr": 3.0, "max_holding_bars": 24}


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

FUNDING_FADE_SHORT = StrategyTemplate(
    family="funding_fade_short",
    direction=Direction.SHORT,
    timeframe="1h",
    param_space={
        "funding_z_min": ParamSpec(1.0, 2.5),
        "rsi_min": ParamSpec(55.0, 75.0),
        **_EXIT_PARAMS,
    },
    base_params={"funding_z_min": 1.5, "rsi_min": 62.0, **_EXIT_BASE},
    entry_builder=_funding_fade_short_entry,
)

FUNDING_FADE_LONG = StrategyTemplate(
    family="funding_fade_long",
    direction=Direction.LONG,
    timeframe="1h",
    param_space={
        "funding_z_max": ParamSpec(-2.5, -1.0),
        "rsi_max": ParamSpec(25.0, 45.0),
        **_EXIT_PARAMS,
    },
    base_params={"funding_z_max": -1.5, "rsi_max": 38.0, **_EXIT_BASE},
    entry_builder=_funding_fade_long_entry,
)

TEMPLATES: dict[str, StrategyTemplate] = {
    t.family: t for t in (
        TREND_PULLBACK, TREND_PULLBACK_SHORT, BREAKOUT, BREAKDOWN_SHORT,
        MEAN_REVERSION, MEAN_REVERSION_SHORT,
        MACD_MOMENTUM, MACD_MOMENTUM_SHORT,
        BOLLINGER_BREAKOUT, BOLLINGER_BREAKDOWN_SHORT,
        HTF_TREND_FOLLOW, HTF_TREND_FOLLOW_SHORT,
        FUNDING_FADE_LONG, FUNDING_FADE_SHORT,
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
    FUNDING_FADE_LONG, FUNDING_FADE_SHORT,
)


def retimed(template: StrategyTemplate, timeframe: str) -> StrategyTemplate:
    """The same template family targeting a different candle timeframe.

    Cost per trade scales inversely with the timeframe's ATR (fees are fixed while
    the stop distance grows), so the same entry shape can be unviable on 1h and
    viable on 1d — measured on 3y BTCUSDT: ~0.21R/trade on 1h vs ~0.031R on 1d.
    The htf_* families cannot be retimed above their own legs (a 1d base has no
    higher 4h view) — their features simply become indeterminate and they never
    fire; prefer excluding them from a 1d run.
    """
    return replace(template, timeframe=str(timeframe))


def templates_for_timeframe(timeframe: str) -> tuple[StrategyTemplate, ...]:
    """The default rotation retimed to ``timeframe``.

    On a timeframe at/above 4h the htf_* families are dropped: their
    higher-timeframe legs cannot be resampled from an equal-or-higher base, so
    they would be generated, validated, and then never match a row.
    """
    tf = str(timeframe)
    order = DEFAULT_TEMPLATE_ORDER
    if tf in {"4h", "1d"}:
        order = tuple(t for t in order if not t.family.startswith("htf_"))
    return tuple(retimed(t, tf) for t in order)
