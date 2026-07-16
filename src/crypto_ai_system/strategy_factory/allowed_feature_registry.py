"""Canonical registry of features a :class:`StrategySpec` may reference.

The whole point of a declarative strategy is that a spec cannot name a feature
that does not exist at evaluation time. The keys enumerated here are exactly the
columns produced by
``crypto_ai_system.features.feature_store.build_feature_frame`` (the runtime
FeatureSnapshot), so a strategy validated against this registry is guaranteed
evaluable on both the live hot path and in backtests — the two share one
feature source.

This module is pure data plus lookups. It does not compute features and does not
validate a spec; the Strategy Validation Agent (Phase S3) consumes these tables.
Keep it in lockstep with ``feature_store``: adding a feature column there and
forgetting it here means strategies simply cannot use it (fail-closed), which is
the safe direction.
"""

from __future__ import annotations

from crypto_ai_system.utils.audit import sha256_json

FEATURE_REGISTRY_VERSION = "allowed_feature_registry.v1"

# Comparison operators, split by operand type. Categorical features support only
# equality — ordering a regime label is meaningless.
NUMERIC_COMPARISONS = frozenset({">", ">=", "<", "<=", "==", "!="})
CATEGORICAL_COMPARISONS = frozenset({"==", "!="})

# Numeric feature columns from build_feature_frame. Every one is computed from
# the current and prior bars only (no look-ahead), so a spec referencing them is
# point-in-time safe by construction.
NUMERIC_FEATURES = frozenset(
    {
        # raw OHLCV
        "open",
        "high",
        "low",
        "close",
        "volume",
        # moving averages / trend
        "ma20",
        "ma50",
        "ema20",
        "ema50",
        "price_distance_ma20",
        # volatility
        "atr",
        "atr_pct_of_price",
        "atr_percentile",
        # momentum / strength
        "rsi",
        "adx",
        # volume
        "volume_ma20",
        # mark / index basis
        "mark_price",
        "index_price",
        "mark_index_basis_bps",
        "mark_last_basis_bps",
        "spread_bps",
        # derivatives
        "funding_rate",
        "funding_zscore",
        "open_interest",
        "open_interest_base",
        "oi_change_pct",
        "oi_change_4h_pct",
        # liquidations
        "long_liquidation",
        "short_liquidation",
        "liquidation_total",
        "liquidation_spike_ratio",
        "liquidation_imbalance",
        "long_liquidation_spike",
        "short_liquidation_spike",
        # multi-timeframe / auxiliary scores
        "mtf_alignment_score",
        "binance_derivatives_score",
        "exchange_flow_score",
        "etf_flow_score",
        "stablecoin_liquidity_score",
    }
)

# Categorical feature columns mapped to their allowed label set. market_regime
# values come from features.regime.classify_market_regime; mtf_bias from
# feature_store's multi-timeframe context.
CATEGORICAL_FEATURES: dict[str, frozenset[str]] = {
    "market_regime": frozenset(
        {"TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNCLEAR"}
    ),
    "mtf_bias": frozenset({"LONG", "SHORT", "NEUTRAL", "UNKNOWN", "DISABLED"}),
}


# Features that are structurally *known* (above) but require a data feed the lean
# runtime does not currently supply. The strategy factory builds both its backtest
# frame and the live router row with derivatives/orderbook/multi-timeframe feeds
# disabled, so feature_store fills these columns with a constant fallback (0, or
# "DISABLED" for mtf_bias). A spec referencing them would not fail closed — it
# would evaluate against fake zeros (always-true or always-false conditions) and
# be silently degenerate in both backtest and live. Until a real feed populates
# them, the validator rejects any spec that references one, keeping the registry's
# "evaluable at evaluation time" guarantee honest. Remove a name from this set
# when its feed is wired into build_backtest_frame / the runtime adapter.
RUNTIME_UNAVAILABLE_FEATURES = frozenset(
    {
        # derivatives (no derivatives feed in the factory/runtime path)
        "funding_rate",
        "funding_zscore",
        "open_interest",
        "open_interest_base",
        "oi_change_pct",
        "oi_change_4h_pct",
        # liquidations (same feed)
        "long_liquidation",
        "short_liquidation",
        "liquidation_total",
        "liquidation_spike_ratio",
        "liquidation_imbalance",
        "long_liquidation_spike",
        "short_liquidation_spike",
        # auxiliary composite scores (require the optional-data collectors)
        "binance_derivatives_score",
        "exchange_flow_score",
        "etf_flow_score",
        "stablecoin_liquidity_score",
        # multi-timeframe context (disabled in the factory/runtime path)
        "mtf_alignment_score",
        "mtf_bias",
    }
)


def is_numeric_feature(name: str) -> bool:
    return name in NUMERIC_FEATURES


def is_runtime_available_feature(name: str) -> bool:
    """True if ``name`` is both a known feature and populated by a live feed.

    A known feature in :data:`RUNTIME_UNAVAILABLE_FEATURES` returns False: it
    exists in the schema but is a constant fallback at evaluation time.
    """
    return is_allowed_feature(name) and name not in RUNTIME_UNAVAILABLE_FEATURES


def is_categorical_feature(name: str) -> bool:
    return name in CATEGORICAL_FEATURES


def is_allowed_feature(name: str) -> bool:
    return is_numeric_feature(name) or is_categorical_feature(name)


def allowed_values_for(name: str) -> frozenset[str] | None:
    """Return the allowed label set for a categorical feature, else None."""
    return CATEGORICAL_FEATURES.get(name)


def allowed_comparisons_for(name: str) -> frozenset[str]:
    """Comparisons valid for ``name``; empty set if the feature is unknown."""
    if is_numeric_feature(name):
        return NUMERIC_COMPARISONS
    if is_categorical_feature(name):
        return CATEGORICAL_COMPARISONS
    return frozenset()


def feature_registry_fingerprint() -> str:
    """Stable hash of the allowed-feature surface.

    Lets downstream evidence bind a strategy to the feature contract it was
    validated against, so a later feature-set change is detectable rather than
    silent.
    """
    return sha256_json(
        {
            "version": FEATURE_REGISTRY_VERSION,
            "numeric": sorted(NUMERIC_FEATURES),
            "categorical": {k: sorted(v) for k, v in sorted(CATEGORICAL_FEATURES.items())},
            "numeric_comparisons": sorted(NUMERIC_COMPARISONS),
            "categorical_comparisons": sorted(CATEGORICAL_COMPARISONS),
        }
    )
