from __future__ import annotations

from config.settings import (
    ALLOW_LIVE_TRADING,
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    ENABLE_REAL_ORDERS,
    ENABLE_TESTNET_ORDERS,
    EXCHANGE_ORDER_ENABLED,
    LIVE_READINESS_PATH,
    LIVE_TRADING_CONFIRMATION,
    LIVE_TRADING_CONFIRMATION_PHRASE,
    LIVE_TRADING_ENABLED,
    MAX_LIVE_POSITION_USDT,
    MAX_ORDER_NOTIONAL_USDT,
    TRADING_MODE,
)
from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


def run_live_readiness_check() -> dict:
    blockers = []
    if TRADING_MODE != "live":
        blockers.append("TRADING_MODE_not_live")
    if not LIVE_TRADING_ENABLED:
        blockers.append("LIVE_TRADING_ENABLED_false")
    if not ALLOW_LIVE_TRADING:
        blockers.append("ALLOW_LIVE_TRADING_false")
    if not EXCHANGE_ORDER_ENABLED:
        blockers.append("EXCHANGE_ORDER_ENABLED_false")
    if not ENABLE_REAL_ORDERS:
        blockers.append("ENABLE_REAL_ORDERS_false")
    if LIVE_TRADING_CONFIRMATION != LIVE_TRADING_CONFIRMATION_PHRASE:
        blockers.append("LIVE_TRADING_CONFIRMATION_mismatch")
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        blockers.append("missing_exchange_api_credentials")
    if MAX_ORDER_NOTIONAL_USDT > MAX_LIVE_POSITION_USDT:
        blockers.append("order_notional_exceeds_live_position_limit")

    result = {
        "created_at": utc_now_iso(),
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "testnet_orders_enabled": ENABLE_TESTNET_ORDERS,
        "max_live_position_usdt": MAX_LIVE_POSITION_USDT,
        "max_order_notional_usdt": MAX_ORDER_NOTIONAL_USDT,
    }
    atomic_write_json(LIVE_READINESS_PATH, result)
    log_event("live_readiness_checked", {"ready": result["ready"], "blockers": blockers})
    return result


def main() -> None:
    result = run_live_readiness_check()
    print(f"Live readiness: ready={result['ready']} blockers={len(result['blockers'])}")


if __name__ == "__main__":
    main()
