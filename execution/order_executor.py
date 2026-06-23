from __future__ import annotations

from config.settings import MAX_ORDER_NOTIONAL_USDT, ORDER_INTENT_PATH, ORDER_RESULT_PATH, TRADE_DECISION_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from execution.idempotency import enrich_order_identity
from execution.live_guard import run_live_readiness_check


def build_order_intent(trade_decision: dict) -> dict:
    if not trade_decision.get("allow_order_intent", False):
        return {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER_INTENT",
            "reason": trade_decision.get("final_decision"),
        }

    direction = trade_decision.get("direction")
    side = "BUY" if direction == "LONG" else "SELL"
    intent = {
        "created_at": utc_now_iso(),
        "state": "CREATED",
        "status": "ORDER_INTENT_CREATED",
        "symbol": trade_decision.get("research", {}).get("symbol", "BTCUSDT"),
        "direction": direction,
        "side": side,
        "order_type": "MARKET_SHADOW",
        "notional_usdt": MAX_ORDER_NOTIONAL_USDT,
        "source_decision": trade_decision.get("final_decision"),
        "confidence": trade_decision.get("confidence", 0),
        "strategy_id": "research_bridge_v2",
        "signal_id": trade_decision.get("final_decision", "unknown_signal"),
        "candle_time": trade_decision.get("data_health", {}).get("latest_candle_time") or trade_decision.get("created_at"),
    }
    return enrich_order_identity(intent)


def execute_order_intent(intent: dict) -> dict:
    readiness = run_live_readiness_check()

    if intent.get("status") != "ORDER_INTENT_CREATED":
        result = {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER",
            "mode": "SKIPPED",
            "intent": intent,
            "readiness": readiness,
        }
    elif not readiness.get("ready", False):
        result = {
            "created_at": utc_now_iso(),
            "state": "VALIDATED",
            "status": "SHADOW_ONLY",
            "mode": "LIVE_BLOCKED_SHADOW_EXECUTION",
            "intent": intent,
            "readiness": readiness,
            "exchange_order_id": None,
            "filled": False,
        }
    else:
        result = {
            "created_at": utc_now_iso(),
            "state": "UNKNOWN",
            "status": "TESTNET_REQUIRED_BEFORE_LIVE",
            "mode": "GUARDED_BLOCK",
            "intent": intent,
            "readiness": readiness,
            "exchange_order_id": None,
            "filled": False,
        }

    atomic_write_json(ORDER_RESULT_PATH, result)
    log_event("order_execution_attempted", {"status": result["status"], "state": result["state"], "client_order_id": intent.get("client_order_id")})
    return result


def run_order_executor() -> dict:
    decision = read_json(TRADE_DECISION_PATH, {})
    intent = build_order_intent(decision)
    atomic_write_json(ORDER_INTENT_PATH, intent)
    return execute_order_intent(intent)


def main() -> None:
    result = run_order_executor()
    print(f"Order executor: {result['status']} state={result['state']}")


if __name__ == "__main__":
    main()
