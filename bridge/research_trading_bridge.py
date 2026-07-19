from __future__ import annotations

from config.settings import (
    DAILY_MAX_LOSS_R,
    DATA_HEALTH_PATH,
    MARKET_SNAPSHOT_PATH,
    MAX_CONSECUTIVE_LOSSES,
    RESEARCH_DECISION_PATH,
    RESEARCH_SIGNAL_PATH,
    RISK_STATUS_PATH,
    TRADE_DECISION_PATH,
    TRADING_CYCLE_PATH,
)
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.decision_pipeline_registry import persist_decision_pipeline_registry_record
from crypto_ai_system.registry.risk_gate_registry import persist_risk_gate_record
from crypto_ai_system.research.paper_profile import get_paper_profile
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate
from crypto_ai_system.trading.trading_decision_agent import build_trading_decision


TRADING_BRIDGE_VERSION = "step292_trading_decision_agent_refactor_v1"
BRIDGE_MODE = "TRADING_DECISION_AGENT_REVIEW_ONLY"
ORDER_INTENT_CREATION_ENABLED_BY_BRIDGE = False
ORDER_ROUTING_ENABLED_BY_BRIDGE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_BRIDGE = False


def decide_trade_action(
    research: dict,
    trading: dict,
    data_health: dict,
    risk: dict,
    *,
    market_snapshot: dict | None = None,
    research_signal: dict | None = None,
    pre_order_risk_gate: dict | None = None,
) -> dict:
    """Create a Step292 trading-decision candidate without creating order intent.

    Price structure decides entry/SL/TP/RR, ResearchSignal-derived permission
    decides allow/reduce/block/review-only, and PreOrderRiskGate is required
    before any order intent can be created. This bridge therefore keeps
    allow_order_intent=False unless a future explicit risk-gate stage passes and
    order-intent creation is deliberately enabled outside this module.
    """
    return build_trading_decision(
        research=research,
        trading=trading,
        data_health=data_health,
        risk=risk,
        market_snapshot=market_snapshot or {},
        research_signal=research_signal or {},
        pre_order_risk_gate=pre_order_risk_gate or {},
    )


def _evaluate_pre_order_gate(
    execution_stage: str,
    research: dict,
    research_signal: dict,
    risk: dict,
    market_snapshot: dict,
    open_positions: int | None = None,
) -> dict:
    """Evaluate the real PreOrderRiskGate for this cycle and persist the record.

    The profile is supplied ONLY for the paper stage (approved paper profile);
    non-paper stages get no approved profile, so the gate blocks on the profile
    gate — signed-testnet/live stay fail-closed here (B-3)."""
    stage = str(execution_stage or "paper").lower()
    profile = get_paper_profile() if stage == "paper" else {}
    # The canonical kernel is authoritative for how many paper positions are open
    # (max_open_positions is enforced by the gate). Fall back to the risk status.
    open_count = int(open_positions if open_positions is not None else (risk.get("open_positions", 0) or 0))
    decision_seed = {
        "decision_id": research.get("decision_id"),
        "side": research.get("side"),
        "direction": research.get("side"),
        "entry": market_snapshot.get("last_close"),
        "entry_price": market_snapshot.get("last_close"),
    }
    runtime_state = {
        "stage": stage,
        "open_positions": open_count,
        "daily_pnl_r": float(risk.get("daily_pnl_r", 0.0) or 0.0),
        "daily_pnl_usdt": float(risk.get("daily_pnl_usdt", 0.0) or 0.0),
        "consecutive_losses": int(risk.get("consecutive_losses", 0) or 0),
        "manual_kill_switch": bool(risk.get("manual_kill_switch", False)),
        "reconciliation_mismatch": bool(risk.get("reconciliation_mismatch", False)),
    }
    market_state = {
        "price": market_snapshot.get("last_close"),
        "mark_price": market_snapshot.get("last_close"),
        "stale": bool(market_snapshot.get("is_stale", False)),
        "synthetic_flag": bool(market_snapshot.get("is_synthetic", False)),
        "fallback_flag": bool(market_snapshot.get("is_fallback", False)),
    }
    gate_config = {
        "stage": stage,
        "max_open_positions": 1,
        "require_profile_hash": True,
        # Loss limits come from settings so the hot-path gate and the cold-path
        # risk_guard judge against the same thresholds (they previously relied
        # on the gate's hardcoded defaults, which drift if the env overrides
        # DAILY_MAX_LOSS_R / MAX_CONSECUTIVE_LOSSES).
        "daily_loss_limit_r": DAILY_MAX_LOSS_R,
        "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
    }
    result = evaluate_pre_order_risk_gate(
        decision=decision_seed,
        research_signal=research_signal,
        profile=profile,
        runtime_state=runtime_state,
        market_state=market_state,
        gate_config=gate_config,
    )
    gate = result.to_dict()
    try:
        # Persist for lineage/verification (the testnet strategy path re-checks
        # this record via the final guard; paper does not need to).
        persist_risk_gate_record(gate, ttl_seconds=300)
    except Exception:  # noqa: BLE001 - persistence is best-effort
        pass
    return gate


def run_research_trading_bridge(execution_stage: str = "paper", *, open_positions: int | None = None) -> dict:
    research = read_json(RESEARCH_DECISION_PATH, {})
    trading = read_json(TRADING_CYCLE_PATH, {})
    data_health = read_json(DATA_HEALTH_PATH, {})
    risk = read_json(RISK_STATUS_PATH, {})
    market_snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    research_signal = read_json(RESEARCH_SIGNAL_PATH, {})

    pre_order_risk_gate = _evaluate_pre_order_gate(
        execution_stage, research, research_signal, risk, market_snapshot, open_positions=open_positions
    )

    policy = decide_trade_action(
        research,
        trading,
        data_health,
        risk,
        market_snapshot=market_snapshot,
        research_signal=research_signal,
        pre_order_risk_gate=pre_order_risk_gate,
    )
    result = {
        "created_at": utc_now_iso(),
        "created_at_utc": policy.get("created_at_utc"),
        "trading_bridge_version": TRADING_BRIDGE_VERSION,
        "bridge_mode": BRIDGE_MODE,
        "research": research,
        "trading_signal": trading.get("trading_signal", {}),
        "data_health": data_health,
        "risk": risk,
        "research_signal": {
            "research_signal_id": research_signal.get("research_signal_id") or research_signal.get("signal_id"),
            "profile_id": research_signal.get("profile_id"),
            "data_snapshot_id": research_signal.get("data_snapshot_id"),
            "feature_snapshot_id": research_signal.get("feature_snapshot_id"),
            "feature_matrix_sha256": research_signal.get("feature_matrix_sha256"),
            "source_bundle_sha256": research_signal.get("source_bundle_sha256"),
            "permission_result": research_signal.get("permission_result"),
            "live_candidate_eligible": research_signal.get("live_candidate_eligible"),
        },
        **policy,
        # Canonical lineage ids the order executor / paper engine require, lifted
        # to the top level from this cycle's gate + decision + signal (B-3).
        "decision_id": research.get("decision_id"),
        "research_signal_id": research_signal.get("research_signal_id") or research_signal.get("signal_id"),
        "profile_id": pre_order_risk_gate.get("profile_id") or research_signal.get("profile_id"),
        "data_snapshot_id": research_signal.get("data_snapshot_id"),
        "feature_snapshot_id": research_signal.get("feature_snapshot_id"),
        "risk_gate_id": pre_order_risk_gate.get("risk_gate_id"),
        "risk_gate_status": pre_order_risk_gate.get("status"),
        "pre_order_risk_gate": pre_order_risk_gate,
        "execution_stage": execution_stage,
        "order_intent_creation_enabled_by_bridge": ORDER_INTENT_CREATION_ENABLED_BY_BRIDGE,
        "order_routing_enabled_by_bridge": ORDER_ROUTING_ENABLED_BY_BRIDGE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_BRIDGE,
    }
    decision_pipeline_record = persist_decision_pipeline_registry_record(
        load_config("."),
        decision=research,
        research_signal=research_signal,
        trade_decision=result,
    )
    result["decision_pipeline_registry_record_id"] = decision_pipeline_record.get("decision_pipeline_record_id")
    result["decision_pipeline_registry_record_sha256"] = decision_pipeline_record.get("decision_pipeline_registry_record_sha256")
    result["decision_pipeline_current_stage_id_chain_complete"] = decision_pipeline_record.get("current_stage_id_chain_complete")
    result["decision_pipeline_missing_current_stage_id_fields"] = decision_pipeline_record.get("missing_current_stage_id_fields") or []
    result["decision_pipeline_missing_canonical_id_fields"] = decision_pipeline_record.get("missing_canonical_id_fields") or []

    atomic_write_json(TRADE_DECISION_PATH, result)
    log_event("trade_decision_created", {"final_decision": result["final_decision"], "allow_order_intent": result["allow_order_intent"]})
    return result


def main() -> None:
    result = run_research_trading_bridge()
    print(f"Trade Decision: {result['final_decision']} allow_order_intent={result['allow_order_intent']}")


if __name__ == "__main__":
    main()
