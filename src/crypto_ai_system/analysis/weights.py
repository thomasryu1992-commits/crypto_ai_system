from __future__ import annotations

DEFAULT_SCORE_WEIGHTS = {
    # Step162 weights: price structure remains primary, extra flow/liquidity data
    # acts as conviction and permission context.
    'structure': 0.20,
    'momentum': 0.10,
    'derivatives': 0.25,
    'exchange_flow': 0.15,
    'etf_flow': 0.15,
    'stablecoin_liquidity': 0.10,
    'risk': 0.05,
    'onchain': 0.00,
}

DEFAULT_THRESHOLDS = {
    'bullish': 0.60,
    'bearish': -0.60,
    'neutral_band': 0.25,
}
