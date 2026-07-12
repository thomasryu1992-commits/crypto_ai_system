from __future__ import annotations

from typing import Dict, Any


def build_extended_ioc_order_payload(trade_plan: Dict[str, Any], orderbook: Dict[str, Any] | None = None, crossing_buffer_bps: float = 10) -> Dict[str, Any]:
    """Build a dry-run Extended-style order payload.

    This module intentionally does not sign or send orders. Step159E should attach
    Stark signing and websocket order-state tracking.
    """
    orderbook = orderbook or {}
    side = trade_plan['side']
    if side == 'LONG':
        ref = float(orderbook.get('ask_price') or trade_plan['entry_reference'])
        price = ref * (1 + crossing_buffer_bps / 10000)
        order_side = 'BUY'
    else:
        ref = float(orderbook.get('bid_price') or trade_plan['entry_reference'])
        price = ref * (1 - crossing_buffer_bps / 10000)
        order_side = 'SELL'
    return {
        'market': trade_plan.get('exchange_market', 'BTC-USD'),
        'side': order_side,
        'type': 'MARKET_OR_IOC_LIMIT_DRY_RUN',
        'price': round(price, 2),
        'qty': trade_plan.get('qty'),
        'timeInForce': 'IOC',
        'reduceOnly': False,
        'clientOrderId': f"dry_{trade_plan.get('symbol', 'BTC-PERP')}_{side}",
        'dry_run': True,
    }
