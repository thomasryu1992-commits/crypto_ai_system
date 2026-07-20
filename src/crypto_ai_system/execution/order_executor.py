from __future__ import annotations

from config.settings import ORDER_INTENT_PATH, ORDER_RESULT_PATH, TRADE_DECISION_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from crypto_ai_system.execution.execution_port import select_adapter
from crypto_ai_system.execution.idempotency import enrich_order_identity
from crypto_ai_system.execution.live_guard import run_live_readiness_check
from crypto_ai_system.trading.order_id_chain import order_intent_id_from_payload


ORDER_EXECUTOR_MODE = "GUARDED_REVIEW_ONLY"
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False


def build_order_intent(trade_decision: dict) -> dict:
    if not trade_decision.get("allow_order_intent", False):
        return {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER_INTENT",
            "reason": trade_decision.get("final_decision"),
            "pre_order_risk_gate_required": bool(trade_decision.get("pre_order_risk_gate_required", True)),
            "pre_order_risk_gate_approved": bool(trade_decision.get("pre_order_risk_gate_approved", False)),
            "order_intent_block_reason": trade_decision.get("order_intent_block_reason") or "PRE_ORDER_RISK_GATE_REQUIRED_BEFORE_ORDER_INTENT",
            "order_intent_created": False,
        }

    # Step292: a trade decision alone cannot create an order intent. Even if a
    # legacy caller passes allow_order_intent=True, the order-intent boundary
    # fails closed unless a PreOrderRiskGate result has explicitly approved it.
    if trade_decision.get("pre_order_risk_gate_approved") is not True or not trade_decision.get("risk_gate_id"):
        return {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER_INTENT",
            "reason": "PRE_ORDER_RISK_GATE_REQUIRED_BEFORE_ORDER_INTENT",
            "pre_order_risk_gate_required": True,
            "pre_order_risk_gate_approved": bool(trade_decision.get("pre_order_risk_gate_approved", False)),
            "risk_gate_id": trade_decision.get("risk_gate_id"),
            "order_intent_block_reason": "PRE_ORDER_RISK_GATE_REQUIRED_BEFORE_ORDER_INTENT",
            "order_intent_created": False,
        }

    direction = str(trade_decision.get("direction") or "").upper()
    if direction not in {"LONG", "SHORT"}:
        # A corrupted/missing direction must never default to a side (it used
        # to map anything non-LONG to SELL — the wrong fail direction).
        return {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER_INTENT",
            "reason": "MALFORMED_DIRECTION",
            "direction": trade_decision.get("direction"),
            "order_intent_block_reason": "MALFORMED_DIRECTION",
            "order_intent_created": False,
        }
    side = "BUY" if direction == "LONG" else "SELL"
    entry_price = trade_decision.get("entry") or trade_decision.get("entry_price") or trade_decision.get("price")
    try:
        entry_float = float(entry_price or 0)
    except Exception:
        entry_float = 0.0
    raw_notional = trade_decision.get("order_notional_usdt") or trade_decision.get("notional_usdt")
    try:
        notional = float(raw_notional) if raw_notional not in {None, ""} else 0.0
    except (TypeError, ValueError):
        notional = 0.0
    if notional <= 0:
        # A missing notional used to default to MAX_ORDER_NOTIONAL_USDT — the
        # cap is a ceiling, never a fallback size. Block instead.
        return {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER_INTENT",
            "reason": "MISSING_ORDER_NOTIONAL",
            "order_intent_block_reason": "MISSING_ORDER_NOTIONAL",
            "order_intent_created": False,
        }
    # No clamp here: MAX_ORDER_NOTIONAL_USDT is the paper cap, and each stage's
    # final guard enforces its own ceiling — a silent resize would desync the
    # intent from the decision the gate approved.
    quantity = trade_decision.get("quantity")
    try:
        quantity_float = float(quantity) if quantity not in {None, ""} else (notional / entry_float if entry_float > 0 else 0.0)
    except Exception:
        quantity_float = 0.0
    intent = {
        "created_at": utc_now_iso(),
        "created_at_utc": trade_decision.get("created_at_utc"),
        "state": "CREATED",
        "status": "ORDER_INTENT_CREATED",
        "decision_stage": trade_decision.get("decision_stage") or trade_decision.get("execution_stage") or "paper",
        "execution_stage": trade_decision.get("execution_stage") or trade_decision.get("decision_stage") or "paper",
        "symbol": trade_decision.get("symbol") or trade_decision.get("research", {}).get("symbol", "BTCUSDT"),
        "direction": direction,
        "side": side,
        "order_type": trade_decision.get("order_type") or "MARKET_PAPER",
        "entry_price": entry_float,
        "stop_loss": trade_decision.get("stop_loss"),
        "take_profit": trade_decision.get("take_profit"),
        "risk_reward": trade_decision.get("risk_reward"),
        "quantity": quantity_float,
        "notional_usdt": notional,
        "order_notional_usdt": notional,
        "source_decision": trade_decision.get("final_decision"),
        "confidence": trade_decision.get("confidence", 0),
        # Strategy-factory attribution when a strategy drove this decision; falls
        # back to the research bridge marker otherwise (S8 lineage).
        "strategy_id": trade_decision.get("strategy_id") or "research_bridge_v2",
        "supporting_strategy_ids": trade_decision.get("supporting_strategy_ids") or [],
        "strategy_entry_evaluation_id": trade_decision.get("strategy_entry_evaluation_id"),
        "strategy_rule_hash": trade_decision.get("strategy_rule_hash"),
        "strategy_generation_id": trade_decision.get("strategy_generation_id"),
        "signal_id": trade_decision.get("research_signal_id") or trade_decision.get("final_decision", "unknown_signal"),
        "research_signal_id": trade_decision.get("research_signal_id") or trade_decision.get("research_signal", {}).get("research_signal_id"),
        "decision_id": trade_decision.get("decision_id"),
        "risk_gate_id": trade_decision.get("risk_gate_id"),
        "profile_id": trade_decision.get("profile_id") or trade_decision.get("research_signal", {}).get("profile_id"),
        "data_snapshot_id": trade_decision.get("data_snapshot_id") or trade_decision.get("research_signal", {}).get("data_snapshot_id"),
        "feature_snapshot_id": trade_decision.get("feature_snapshot_id") or trade_decision.get("research_signal", {}).get("feature_snapshot_id"),
        "pre_order_risk_gate_required": bool(trade_decision.get("pre_order_risk_gate_required", True)),
        "pre_order_risk_gate_approved": bool(trade_decision.get("pre_order_risk_gate_approved", False)),
        "risk_gate_status": trade_decision.get("risk_gate_status"),
        "risk_gate_report": trade_decision.get("pre_order_risk_gate") or trade_decision.get("risk_gate_report") or {},
        "paper_execution_requested": True,
        "order_intent_created": True,
        "adapter_called": False,
        "live_order_executed": False,
        "external_order_submission_performed": False,
        "candle_time": trade_decision.get("data_health", {}).get("latest_candle_time") or trade_decision.get("created_at"),
    }
    intent["order_intent_id"] = trade_decision.get("order_intent_id") or order_intent_id_from_payload(intent)
    return enrich_order_identity(intent)


def execute_order_intent(intent: dict) -> dict:
    readiness = run_live_readiness_check()

    stage = str(intent.get("execution_stage") or intent.get("decision_stage") or "").lower()
    adapter = select_adapter(stage)
    if intent.get("status") != "ORDER_INTENT_CREATED":
        result = {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER",
            "mode": "SKIPPED",
            "intent": intent,
            "readiness": readiness,
        }
    elif adapter is not None:
        # Same canonical OrderIntent, stage-selected venue adapter (P0-1). The
        # only paper/testnet difference is the adapter; RiskGate/reconciliation
        # are shared upstream/downstream.
        result = adapter.submit(intent, readiness=readiness)
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

    result["order_executor_mode"] = ORDER_EXECUTOR_MODE
    result["live_trading_allowed_by_this_module"] = LIVE_TRADING_ALLOWED_BY_THIS_MODULE
    result["adapter_routing_enabled_by_this_module"] = ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE
    # A branch (e.g. signed testnet) may have already recorded a real submission;
    # only default this to the module constant when the branch did not set it.
    result.setdefault("external_order_submission_performed", EXTERNAL_ORDER_SUBMISSION_PERFORMED)
    atomic_write_json(ORDER_RESULT_PATH, result)
    log_event("order_execution_attempted", {"status": result["status"], "state": result["state"], "client_order_id": intent.get("client_order_id")})
    return result


def place_order(order: dict) -> dict:
    """Legacy test-compatible hard block for direct order placement.

    Real orders must go through build_order_intent -> execute_order_intent, and live
    execution remains disabled unless all explicit safety gates pass.
    """
    result = {
        "created_at": utc_now_iso(),
        "status": "BLOCKED_STEP80",
        "state": "REJECTED",
        "mode": "DIRECT_ORDER_BLOCKED",
        "reason": "direct place_order is disabled; use guarded order intent pipeline",
        "order": order,
        "order_executor_mode": ORDER_EXECUTOR_MODE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "adapter_routing_enabled_by_this_module": ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
    }
    atomic_write_json(ORDER_RESULT_PATH, result)
    log_event("direct_order_blocked", {"status": result["status"]})
    return result


def execute_order_with_risk_check(
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float | None = None,
    current_price: float | None = None,
    storage_dir: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Guarded review-only compatibility boundary for order-executor bridge callers.

    This function intentionally does not submit exchange orders. It creates a
    deterministic blocked/review-only result that preserves request metadata for
    downstream audit flows.
    """
    request = {
        "created_at": utc_now_iso(),
        "request_id": f"order_request_{utc_now_iso()}",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "current_price": current_price,
        "metadata": dict(metadata or {}),
    }
    result = {
        "created_at": utc_now_iso(),
        "status": "GUARDED_REVIEW_ONLY_BLOCKED",
        "state": "REJECTED",
        "mode": ORDER_EXECUTOR_MODE,
        "executed": False,
        "filled": False,
        "exchange_order_id": None,
        "reason": "canonical order executor bridge is review-only; external order submission is disabled",
        "order_request": request,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "adapter_routing_enabled_by_this_module": ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
    }
    log_event("order_executor_bridge_blocked", {"status": result["status"], "symbol": symbol, "side": side})
    return result


def run_order_executor(execution_stage: str | None = None) -> dict:
    decision = read_json(TRADE_DECISION_PATH, {})
    if decision.get("order_intent_consumed_at"):
        # One persisted decision authorizes AT MOST one intent. Re-running the
        # executor against the same file (e.g. a manual `py -m ...order_executor`
        # inside the RiskGate record's TTL) must not re-submit.
        intent = {
            "created_at": utc_now_iso(),
            "state": "REJECTED",
            "status": "NO_ORDER_INTENT",
            "reason": "TRADE_DECISION_ALREADY_CONSUMED",
            "order_intent_block_reason": "TRADE_DECISION_ALREADY_CONSUMED",
            "consumed_at": decision.get("order_intent_consumed_at"),
            "consumed_by_order_intent_id": decision.get("consumed_by_order_intent_id"),
            "order_intent_created": False,
        }
        atomic_write_json(ORDER_INTENT_PATH, intent)
        return execute_order_intent(intent)
    intent = build_order_intent(decision)
    if execution_stage and intent.get("status") == "ORDER_INTENT_CREATED":
        intent["execution_stage"] = execution_stage
        intent["decision_stage"] = execution_stage
    if intent.get("status") == "ORDER_INTENT_CREATED":
        decision["order_intent_consumed_at"] = utc_now_iso()
        decision["consumed_by_order_intent_id"] = intent.get("order_intent_id")
        atomic_write_json(TRADE_DECISION_PATH, decision)
    atomic_write_json(ORDER_INTENT_PATH, intent)
    return execute_order_intent(intent)


def main() -> None:
    result = run_order_executor()
    print(f"Order executor: {result['status']} state={result['state']}")


if __name__ == "__main__":
    main()
