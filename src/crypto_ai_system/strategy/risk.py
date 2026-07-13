from __future__ import annotations


def calculate_position_size(equity: float, risk_per_trade_pct: float, entry: float, stop: float) -> tuple[float, float, float]:
    """Return (qty, risk_amount, risk_per_unit).

    Older code expected only qty, but TradingBot already consumes the full risk tuple.
    This shape is the canonical Step158 interface.
    """
    risk_amount = float(equity) * float(risk_per_trade_pct)
    risk_per_unit = abs(float(entry) - float(stop))
    if risk_per_unit <= 0:
        return 0.0, risk_amount, risk_per_unit
    return risk_amount / risk_per_unit, risk_amount, risk_per_unit


def clamp_stop_distance(entry: float, raw_stop: float, side: str, min_bps: float, max_bps: float) -> float:
    dist = abs(entry - raw_stop)
    min_dist = entry * min_bps / 10000
    max_dist = entry * max_bps / 10000
    clamped = min(max(dist, min_dist), max_dist)
    if side == 'LONG':
        return entry - clamped
    if side == 'SHORT':
        return entry + clamped
    raise ValueError(f'Invalid side: {side}')
