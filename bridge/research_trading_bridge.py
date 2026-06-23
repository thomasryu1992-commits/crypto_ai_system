from __future__ import annotations

from config.settings import DATA_HEALTH_PATH, RESEARCH_DECISION_PATH, RISK_STATUS_PATH, TRADE_DECISION_PATH, TRADING_CYCLE_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


def decide_trade_action(research: dict, trading: dict, data_health: dict, risk: dict) -> dict:
    reasons = []
    signal_payload = trading.get("trading_signal", {})
    signal = signal_payload.get("signal", "NONE")
    confidence = int(signal_payload.get("confidence", 0) or 0)

    if not data_health.get("allow_trading", False):
        return {
            "final_decision": "BLOCK_DATA_HEALTH",
            "allow_order_intent": False,
            "direction": "NONE",
            "confidence": 0,
            "reasons": ["data_health_disallows_trading"] + data_health.get("problems", []),
        }

    if data_health.get("is_synthetic") or data_health.get("is_fallback"):
        return {
            "final_decision": "BLOCK_SYNTHETIC_DATA",
            "allow_order_intent": False,
            "direction": "NONE",
            "confidence": 0,
            "reasons": ["synthetic_or_fallback_data_blocked"],
        }

    if not risk.get("allow_new_position", False):
        return {
            "final_decision": "BLOCK_RISK",
            "allow_order_intent": False,
            "direction": "NONE",
            "confidence": 0,
            "reasons": ["risk_guard_disallows_new_position"] + risk.get("problems", []),
        }

    scenario = research.get("scenario")
    timing = research.get("signal_timing")
    allow_long = bool(research.get("allow_long"))
    allow_short = bool(research.get("allow_short"))

    if signal == "NONE":
        if scenario in {"Bullish", "Constructive"}:
            return {
                "final_decision": "WATCH_LONG",
                "allow_order_intent": False,
                "direction": "NONE",
                "confidence": confidence,
                "reasons": ["research_constructive_but_no_trading_signal"],
            }
        if scenario == "Bearish":
            return {
                "final_decision": "WATCH_SHORT",
                "allow_order_intent": False,
                "direction": "NONE",
                "confidence": confidence,
                "reasons": ["research_bearish_but_no_trading_signal"],
            }
        return {
            "final_decision": "NO_ACTION",
            "allow_order_intent": False,
            "direction": "NONE",
            "confidence": confidence,
            "reasons": ["no_trading_signal"],
        }

    if timing in {"Late", "Data-Blocked"}:
        return {
            "final_decision": "BLOCK_LATE_OR_DATA_BLOCKED",
            "allow_order_intent": False,
            "direction": "NONE",
            "confidence": confidence,
            "reasons": [f"signal_timing_{timing}"],
        }

    if signal == "LONG" and allow_long:
        return {
            "final_decision": "ALLOW_PAPER_LONG",
            "allow_order_intent": True,
            "direction": "LONG",
            "confidence": confidence,
            "reasons": ["research_and_trading_aligned_long"],
        }

    if signal == "SHORT" and allow_short:
        return {
            "final_decision": "ALLOW_PAPER_SHORT",
            "allow_order_intent": True,
            "direction": "SHORT",
            "confidence": confidence,
            "reasons": ["research_and_trading_aligned_short"],
        }

    return {
        "final_decision": "BLOCK_CONFLICTING_SIGNAL",
        "allow_order_intent": False,
        "direction": "NONE",
        "confidence": confidence,
        "reasons": [f"signal_{signal}_conflicts_with_research_bias_{research.get('research_bias')}"],
    }


def run_research_trading_bridge() -> dict:
    research = read_json(RESEARCH_DECISION_PATH, {})
    trading = read_json(TRADING_CYCLE_PATH, {})
    data_health = read_json(DATA_HEALTH_PATH, {})
    risk = read_json(RISK_STATUS_PATH, {})

    policy = decide_trade_action(research, trading, data_health, risk)
    result = {
        "created_at": utc_now_iso(),
        "research": research,
        "trading_signal": trading.get("trading_signal", {}),
        "data_health": data_health,
        "risk": risk,
        **policy,
    }
    atomic_write_json(TRADE_DECISION_PATH, result)
    log_event("trade_decision_created", {"final_decision": result["final_decision"], "allow_order_intent": result["allow_order_intent"]})
    return result


def main() -> None:
    result = run_research_trading_bridge()
    print(f"Trade Decision: {result['final_decision']} allow_order_intent={result['allow_order_intent']}")


if __name__ == "__main__":
    main()
