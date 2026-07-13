from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

import numpy as np
import pandas as pd

from crypto_ai_system.analysis.weights import DEFAULT_SCORE_WEIGHTS


def _clip(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    try:
        if pd.isna(v) or np.isinf(v):
            return 0.0
    except TypeError:
        pass
    return float(max(lo, min(hi, v)))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        if pd.isna(v) or np.isinf(v):
            return default
        return v
    except Exception:
        return default


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    merged = dict(DEFAULT_SCORE_WEIGHTS)
    if weights:
        merged.update({k: float(v) for k, v in weights.items() if v is not None})
    total = sum(max(0.0, float(v)) for v in merged.values())
    if total <= 0:
        return dict(DEFAULT_SCORE_WEIGHTS)
    return {k: max(0.0, float(v)) / total for k, v in merged.items()}


@dataclass
class ScoreBreakdown:
    structure: float
    momentum: float
    derivatives: float
    exchange_flow: float
    etf_flow: float
    stablecoin_liquidity: float
    risk: float
    onchain: float
    total_score: float
    bias: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScoreEngine:
    """Weighted scoring engine for raw/feature data.

    Output range is roughly [-1, +1]. The extra-data layer is included as
    separate components so ResearchSignal can explain whether the conviction came
    from price, derivatives, exchange flow, ETF flow, or stablecoin liquidity.
    """

    def __init__(self, weights: Dict[str, float] | None = None):
        self.weights = _normalize_weights(weights or DEFAULT_SCORE_WEIGHTS)

    def score_row(self, row: pd.Series | Dict[str, Any]) -> ScoreBreakdown:
        r = row if isinstance(row, dict) else row.to_dict()
        close = _as_float(r.get('close'))
        ma20 = _as_float(r.get('ma20'), close or 1)
        ma50 = _as_float(r.get('ma50'), close or 1)
        rsi = _as_float(r.get('rsi'), 50)
        adx = _as_float(r.get('adx'), 0)
        funding_z = _as_float(r.get('funding_zscore'), 0)
        oi_change = _as_float(r.get('oi_change_pct'), 0)
        atr_pct = _as_float(r.get('atr_pct_of_price'), 0)
        spread_bps = _as_float(r.get('spread_bps'), 0)
        mark_basis = _as_float(r.get('mark_index_basis_bps'), 0)
        liq_imb = _as_float(r.get('liquidation_imbalance'), 0)
        mtf_alignment = _as_float(r.get('mtf_alignment_score'), 0)
        binance_derivatives_score = _as_float(r.get('binance_derivatives_score'), 0)

        structure = 0.0
        if close > ma20 > ma50:
            structure += 0.7
        elif close < ma20 < ma50:
            structure -= 0.7
        structure += _clip((close - ma20) / ma20 / 0.02 if ma20 else 0) * 0.25
        structure += _clip(mtf_alignment) * 0.15
        structure = _clip(structure)

        momentum = _clip((rsi - 50) / 25)
        if adx >= 20:
            momentum *= 1.15
        momentum = _clip(momentum)

        core_derivatives = 0.0
        core_derivatives += _clip(oi_change / 0.02) * 0.35
        core_derivatives += _clip(-funding_z / 3.0) * 0.20
        core_derivatives += _clip(mark_basis / 20.0) * 0.15
        core_derivatives += _clip(liq_imb) * 0.30
        core_derivatives = _clip(core_derivatives)
        derivatives = _clip(core_derivatives * 0.75 + _clip(binance_derivatives_score) * 0.25)

        exchange_flow = _clip(_as_float(r.get('exchange_flow_score'), 0.0))
        etf_flow = _clip(_as_float(r.get('etf_flow_score'), 0.0))
        stablecoin_liquidity = _clip(_as_float(r.get('stablecoin_liquidity_score'), 0.0))

        risk = 0.0
        risk -= _clip(atr_pct / 0.035) * 0.50
        risk -= _clip(spread_bps / 15.0) * 0.50
        # Exchange-flow sell-pressure and crowded derivatives are not directional only;
        # they also reduce trade permission quality when extreme.
        risk -= max(0.0, -exchange_flow - 0.4) * 0.15
        risk -= max(0.0, abs(binance_derivatives_score) - 0.75) * 0.10
        risk = _clip(risk)

        onchain = _clip(_as_float(r.get('onchain_score'), 0.0))

        total = (
            structure * self.weights.get('structure', 0)
            + momentum * self.weights.get('momentum', 0)
            + derivatives * self.weights.get('derivatives', 0)
            + exchange_flow * self.weights.get('exchange_flow', 0)
            + etf_flow * self.weights.get('etf_flow', 0)
            + stablecoin_liquidity * self.weights.get('stablecoin_liquidity', 0)
            + risk * self.weights.get('risk', 0)
            + onchain * self.weights.get('onchain', 0)
        )
        total = _clip(total)
        bias = 'BULLISH' if total >= 0.25 else 'BEARISH' if total <= -0.25 else 'NEUTRAL'
        return ScoreBreakdown(structure, momentum, derivatives, exchange_flow, etf_flow, stablecoin_liquidity, risk, onchain, total, bias)

    def score_frame(self, features: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, row in features.iterrows():
            rows.append(self.score_row(row).to_dict())
        scored_df = features.copy().reset_index(drop=True)
        score_df = pd.DataFrame(rows)
        return pd.concat([scored_df, score_df.add_prefix('score_')], axis=1)
