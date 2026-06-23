from __future__ import annotations

from core.json_io import append_jsonl
from core.time_utils import utc_now_iso
from config.settings import ENABLE_TESTNET_ORDERS, TESTNET_ORDER_LOG_PATH
from execution.retry_policy import classify_exchange_error


class TestnetExecutor:
    """Guarded Binance testnet skeleton.

    In Step150 this does not send network orders by default.
    Set ENABLE_TESTNET_ORDERS=true only after implementing signed REST calls and tests.
    """

    def place_order(self, intent: dict) -> dict:
        if not ENABLE_TESTNET_ORDERS:
            result = {
                "created_at": utc_now_iso(),
                "state": "VALIDATED",
                "status": "TESTNET_ORDER_SKIPPED",
                "reason": "ENABLE_TESTNET_ORDERS_false",
                "intent_id": intent.get("intent_id"),
                "client_order_id": intent.get("client_order_id"),
            }
            append_jsonl(TESTNET_ORDER_LOG_PATH, result)
            return result

        raise NotImplementedError("Signed Binance testnet orders are not implemented in guarded Step150 package.")

    def recover_unknown_order(self, client_order_id: str) -> dict:
        # Scaffold for timeout / 429 recovery.
        result = {
            "created_at": utc_now_iso(),
            "state": "UNKNOWN",
            "status": "RECOVERY_QUERY_NOT_IMPLEMENTED",
            "client_order_id": client_order_id,
            "policy": classify_exchange_error(error_name="timeout"),
        }
        append_jsonl(TESTNET_ORDER_LOG_PATH, result)
        return result
