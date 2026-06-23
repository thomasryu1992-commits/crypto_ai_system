from __future__ import annotations

from config.settings import MAX_POSITION_NOTIONAL_USDT, POSITION_SIZE_ACCOUNT_EQUITY_USDT, RISK_PER_TRADE


def calculate_position_size(entry_price: float, stop_loss: float) -> dict:
    stop_distance = abs(entry_price - stop_loss)
    if entry_price <= 0 or stop_distance <= 0:
        return {"quantity": 0.0, "notional_usdt": 0.0, "risk_usdt": 0.0, "reason": "invalid_entry_or_stop"}

    risk_usdt = POSITION_SIZE_ACCOUNT_EQUITY_USDT * RISK_PER_TRADE
    quantity = risk_usdt / stop_distance
    notional = quantity * entry_price

    if notional > MAX_POSITION_NOTIONAL_USDT:
        notional = MAX_POSITION_NOTIONAL_USDT
        quantity = notional / entry_price

    return {
        "quantity": round(quantity, 8),
        "notional_usdt": round(notional, 4),
        "risk_usdt": round(risk_usdt, 4),
        "reason": "position_size_by_risk_with_notional_cap",
    }
