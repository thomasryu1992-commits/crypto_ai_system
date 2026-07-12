from __future__ import annotations

from typing import Any, Dict

from config.settings import LINT_DIR, STORAGE_DIR, env_bool, ensure_base_dirs
from crypto_ai_system.execution.execution_reconciler import run_execution_reconciliation
from scripts.json_utils import load_json, now_utc_iso, save_json
from trading_bot.bot_state_manager import build_bot_state
from trading_bot.order_executor_bridge import run_order_executor_bridge
from trading_bot.paper_performance_reporter import generate_paper_performance_report
from trading_bot.paper_position_manager import run_paper_position_update
from trading_bot.paper_watch_manager import run_paper_watch_update
from trading_bot.setup_decision_gate import run_setup_decision_gate
from trading_bot.setup_performance_analyzer import analyze_setup_performance
from trading_bot.setup_weight_engine import build_setup_weight_report


def run_trading_bot() -> Dict[str, Any]:
    ensure_base_dirs()

    market_context = load_json(STORAGE_DIR / "market_context.json", default={})
    research_decision = load_json(STORAGE_DIR / "research_decision.json", default={})
    kb_lint_result = load_json(LINT_DIR / "kb_lint_result.json", default={})

    if env_bool("KB_LINT_BLOCK_TRADING_ON_ERROR", True) and kb_lint_result.get("status") == "ERROR":
        result = {
            "status": "BLOCKED_BY_KB_LINT",
            "timestamp_utc": now_utc_iso(),
            "reason": "KB lint status is ERROR.",
            "kb_lint_status": kb_lint_result.get("status"),
            "symbol": research_decision.get("symbol") if isinstance(research_decision, dict) else None,
            "decision_type": research_decision.get("decision_type") if isinstance(research_decision, dict) else None,
            "decision_source": research_decision.get("decision_source") if isinstance(research_decision, dict) else None,
        }
        save_json(STORAGE_DIR / "trading_bot_result.json", result)
        return result

    setup_performance_report = analyze_setup_performance(STORAGE_DIR)
    setup_weight_report = build_setup_weight_report(STORAGE_DIR)
    setup_gate_result = run_setup_decision_gate(research_decision, STORAGE_DIR)

    paper_watch_result = run_paper_watch_update(
        research_decision,
        market_context,
        setup_gate_result,
        STORAGE_DIR,
    )

    paper_position_result = run_paper_position_update(
        paper_watch_result,
        market_context,
        STORAGE_DIR,
    )

    paper_performance_report = generate_paper_performance_report(STORAGE_DIR)
    bot_state = build_bot_state(STORAGE_DIR)

    bridge_result = run_order_executor_bridge(
        paper_watch_result,
        paper_position_result,
        market_context,
        STORAGE_DIR,
    )

    reconciliation_result = run_execution_reconciliation(STORAGE_DIR)

    status = _resolve_status(
        research_decision=research_decision,
        watch_result=paper_watch_result,
        position_result=paper_position_result,
        bridge_result=bridge_result,
        bot_state=bot_state,
        setup_gate_result=setup_gate_result,
    )

    result = {
        "status": status,
        "timestamp_utc": now_utc_iso(),
        "symbol": market_context.get("symbol") or research_decision.get("symbol", "BTCUSDT"),
        "input_summary": {
            "current_price": market_context.get("current_price"),
            "kb_lint_status": kb_lint_result.get("status"),
        },
        "research_decision_summary": _research_decision_summary(research_decision),
        "setup_decision_gate_status": setup_gate_result.get("status"),
        "setup_decision_gate_summary": setup_gate_result,
        "paper_watch_summary": paper_watch_result.get("summary", {}),
        "paper_watch_status": paper_watch_result.get("status"),
        "paper_position_summary": paper_position_result.get("summary", {}),
        "paper_position_status": paper_position_result.get("status"),
        "paper_performance_summary": paper_performance_report,
        "setup_weight_summary": {
            key: setup_weight_report.get(key)
            for key in [
                "setup_count",
                "tradable_setup_count",
                "observe_only_setup_count",
                "disabled_setup_count",
            ]
        },
        "order_executor_bridge_status": bridge_result.get("status"),
        "order_executor_bridge_summary": {
            "enabled": bridge_result.get("enabled"),
            "open_event_count": bridge_result.get("open_event_count"),
            "bridge_event_count": bridge_result.get("bridge_event_count"),
            "order_execution_count": bridge_result.get("order_execution_count"),
            "reason": bridge_result.get("reason"),
        },
        "execution_reconciliation_status": reconciliation_result.get("status"),
        "execution_reconciliation_summary": {
            "status": reconciliation_result.get("status"),
            "reconciled": reconciliation_result.get("reconciled"),
            "failed_check_count": (
                len(reconciliation_result.get("failed_checks", []))
                if isinstance(reconciliation_result.get("failed_checks"), list)
                else None
            ),
        },
        "bot_state_summary": bot_state,
        "watch_events": paper_watch_result.get("events", []),
        "position_events": paper_position_result.get("events", []),
        "safety": {
            "live_trading_enabled": False,
            "exchange_order_execution": False,
            "order_executor_bridge_enabled": env_bool("ORDER_EXECUTOR_INTEGRATION_ENABLED", False),
        },
    }

    save_json(STORAGE_DIR / "trading_bot_result.json", result)
    return result


def _resolve_status(
    research_decision: Dict[str, Any],
    watch_result: Dict[str, Any],
    position_result: Dict[str, Any],
    bridge_result: Dict[str, Any],
    bot_state: Dict[str, Any],
    setup_gate_result: Dict[str, Any],
) -> str:
    decision_type = str(research_decision.get("decision_type") or "").upper() if isinstance(research_decision, dict) else ""
    watch_status = watch_result.get("status")
    position_status = position_result.get("status")
    bridge_status = bridge_result.get("status")
    gate_status = setup_gate_result.get("status")

    open_position_count = _nested_int(bot_state, ["counts", "open_position_count"])
    active_watch_count = _nested_int(bot_state, ["counts", "active_watch_count"])

    if position_status == "PAPER_POSITION_OPENED":
        return "PAPER_POSITION_OPENED"

    if position_status in {"PAPER_POSITION_CLOSED_TP", "PAPER_POSITION_CLOSED_SL"}:
        return str(position_status)

    if watch_status == "PAPER_WATCH_CREATED":
        return "PAPER_WATCH_CREATED"

    if watch_status == "PAPER_WATCH_TRIGGERED":
        return "PAPER_WATCH_TRIGGERED"

    if watch_status == "PAPER_WATCH_INVALIDATED":
        return "PAPER_WATCH_INVALIDATED"

    if bridge_status == "MOCK_ORDER_ACCEPTED":
        return "MOCK_ORDER_ACCEPTED"

    if decision_type == "OBSERVE_ONLY" and active_watch_count == 0 and open_position_count == 0:
        return "OBSERVE_ONLY"

    if gate_status == "OBSERVE_ONLY" and active_watch_count == 0 and open_position_count == 0:
        return "OBSERVE_ONLY"

    return "CYCLE_NO_ACTION"


def _research_decision_summary(research_decision: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(research_decision, dict):
        return {}

    conditional_setup = research_decision.get("conditional_setup")

    summary = {
        "status": research_decision.get("status"),
        "decision_type": research_decision.get("decision_type"),
        "decision_source": research_decision.get("decision_source"),
        "symbol": research_decision.get("symbol"),
        "current_price": research_decision.get("current_price"),
        "trading_bias": research_decision.get("trading_bias"),
        "confidence": research_decision.get("confidence"),
        "reason": research_decision.get("reason"),
        "has_conditional_setup": isinstance(conditional_setup, dict),
    }

    if isinstance(conditional_setup, dict):
        summary["conditional_setup"] = {
            "setup_type": conditional_setup.get("setup_type"),
            "direction": conditional_setup.get("direction"),
            "trigger_price": conditional_setup.get("trigger_price"),
            "invalidation_price": conditional_setup.get("invalidation_price"),
            "take_profit": conditional_setup.get("take_profit"),
            "source": conditional_setup.get("source"),
        }

    return summary


def _nested_int(data: Dict[str, Any], path: list[str]) -> int:
    current: Any = data

    for key in path:
        if not isinstance(current, dict):
            return 0
        current = current.get(key)

    try:
        return int(current)
    except (TypeError, ValueError):
        return 0


def main() -> None:
    result = run_trading_bot()
    _print_summary(result)

    if result.get("status") == "BLOCKED_BY_KB_LINT":
        raise SystemExit(1)


def _print_summary(result: Dict[str, Any]) -> None:
    decision = result.get("research_decision_summary", {})

    print("=" * 80)
    print("[TRADING BOT]")
    print("=" * 80)
    print(f"Status: {result.get('status')}")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Current Price: {result.get('input_summary', {}).get('current_price')}")
    print(f"KB Lint Status: {result.get('input_summary', {}).get('kb_lint_status')}")
    print(f"Decision Type: {decision.get('decision_type')}")
    print(f"Decision Source: {decision.get('decision_source')}")
    print(f"Has Conditional Setup: {decision.get('has_conditional_setup')}")
    print(f"Setup Gate: {result.get('setup_decision_gate_status')}")
    print(f"Paper Watch: {result.get('paper_watch_status')}")
    print(f"Paper Position: {result.get('paper_position_status')}")
    print(f"Bridge: {result.get('order_executor_bridge_status')}")
    print(f"Reconciliation: {result.get('execution_reconciliation_status')}")

    if result.get("status") == "OBSERVE_ONLY":
        print("-" * 80)
        print("[OBSERVE ONLY]")
        print(decision.get("reason") or "Market signal is weak or mixed. No new paper watch created.")


if __name__ == "__main__":
    main()