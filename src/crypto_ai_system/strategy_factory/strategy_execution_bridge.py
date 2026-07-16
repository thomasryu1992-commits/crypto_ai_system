"""Increment 2 orchestration: assemble a strategy-driven trade decision.

Sits between the router (S7) and the existing order executor. Given the router's
entry candidate for this cycle, it gathers everything the decision needs — the
primary strategy's spec from the active pool, the live feature row, the research
permission for the strategy's direction, and a fresh PreOrderRiskGate evaluated
for that direction — and produces a canonical trade decision (with S8
attribution). The trading agent persists that decision so the *unchanged* order
executor + paper kernel carry it, exactly like a research-driven entry.

Returns ``None`` whenever a strategy entry should not be created (no candidate,
unknown primary, missing data). The decision it does return still fails closed
via ``allow_order_intent`` — this bridge assembles evidence, it does not grant
execution.
"""

from __future__ import annotations

from typing import Any, Mapping

import config.settings as settings
from core.json_io import read_json

from crypto_ai_system.research.paper_profile import get_paper_profile
from crypto_ai_system.strategy_factory.entry_strategy_router_agent import STATUS_ENTRY_CANDIDATE
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_runtime_feature_row
from crypto_ai_system.strategy_factory.strategy_outcome_attribution import build_strategy_attribution
from crypto_ai_system.strategy_factory.strategy_trade_decision import build_strategy_trade_decision
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate
from crypto_ai_system.trading.trading_decision_agent import build_research_permission_decision


def _primary_spec(pool: Mapping[str, Any], strategy_id: str) -> dict | None:
    for entry in (pool.get("active_strategies") or []):
        if entry.get("strategy_id") == strategy_id and entry.get("strategy_spec"):
            return dict(entry["strategy_spec"])
    return None


def _evaluate_strategy_risk_gate(
    direction: str,
    *,
    execution_stage: str,
    research_signal: Mapping[str, Any],
    risk: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    open_positions: int,
    eval_id: str | None,
) -> dict[str, Any]:
    """Evaluate the hot-path PreOrderRiskGate for the strategy's direction.

    Mirrors the research bridge's gate call but seeds the decision with the
    strategy direction. Paper is the only stage given an approved profile."""
    stage = str(execution_stage or "paper").lower()
    profile = get_paper_profile() if stage == "paper" else {}
    price = market_snapshot.get("last_close")
    decision_seed = {"decision_id": eval_id, "side": direction, "direction": direction,
                     "entry": price, "entry_price": price}
    runtime_state = {
        "stage": stage,
        "open_positions": int(open_positions),
        "daily_pnl_r": float(risk.get("daily_pnl_r", 0.0) or 0.0),
        "daily_pnl_usdt": float(risk.get("daily_pnl_usdt", 0.0) or 0.0),
        "consecutive_losses": int(risk.get("consecutive_losses", 0) or 0),
        "manual_kill_switch": bool(risk.get("manual_kill_switch", False)),
        "reconciliation_mismatch": bool(risk.get("reconciliation_mismatch", False)),
    }
    market_state = {
        "price": price, "mark_price": price,
        "stale": bool(market_snapshot.get("is_stale", False)),
        "synthetic_flag": bool(market_snapshot.get("is_synthetic", False)),
        "fallback_flag": bool(market_snapshot.get("is_fallback", False)),
    }
    gate_config = {"stage": stage, "max_open_positions": 1, "require_profile_hash": True}
    result = evaluate_pre_order_risk_gate(
        decision=decision_seed, research_signal=research_signal, profile=profile,
        runtime_state=runtime_state, market_state=market_state, gate_config=gate_config,
    )
    return result.to_dict()


def build_strategy_decision_for_cycle(
    strategy_routing: Mapping[str, Any],
    *,
    execution_stage: str = "paper",
    open_positions: int = 0,
    cycle_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Build the strategy trade decision for this cycle, or None if not applicable."""
    if not strategy_routing or strategy_routing.get("status") != STATUS_ENTRY_CANDIDATE:
        return None
    direction = str(strategy_routing.get("direction") or "").upper()
    if direction not in {"LONG", "SHORT"}:
        return None

    pool = read_json(settings.ACTIVE_STRATEGY_POOL_PATH, {}) or {}
    primary_spec = _primary_spec(pool, strategy_routing.get("primary_strategy_id"))
    if not primary_spec:
        return None

    market_snapshot = read_json(settings.MARKET_SNAPSHOT_PATH, {}) or {}
    research_signal = read_json(settings.RESEARCH_SIGNAL_PATH, {}) or {}
    risk = read_json(settings.RISK_STATUS_PATH, {}) or {}
    market_data = read_json(settings.MARKET_DATA_PATH, {}) or {}
    candles = market_data.get("candles", []) if isinstance(market_data, dict) else []
    feature_row = build_runtime_feature_row(candles)

    permission = build_research_permission_decision(
        research={}, signal_payload={"signal": direction}, research_signal=research_signal
    ).to_dict()

    attribution = build_strategy_attribution(strategy_routing, primary_spec, cycle_id=cycle_id)

    gate = _evaluate_strategy_risk_gate(
        direction, execution_stage=execution_stage, research_signal=research_signal,
        risk=risk, market_snapshot=market_snapshot, open_positions=open_positions,
        eval_id=attribution.get("strategy_entry_evaluation_id"),
    )

    symbol = str(market_snapshot.get("symbol") or primary_spec.get("symbol_scope", ["BTCUSDT"])[0])
    notional = float(getattr(settings, "MAX_ORDER_NOTIONAL_USDT", 20.0))
    return build_strategy_trade_decision(
        router_result=strategy_routing, primary_spec=primary_spec, feature_row=feature_row,
        market_snapshot=market_snapshot, research_permission=permission, pre_order_risk_gate=gate,
        attribution=attribution, symbol=symbol, notional_usdt=notional,
        execution_stage=execution_stage,
        # The cycle's data lineage the paper engine requires on the intent.
        research_signal_id=research_signal.get("research_signal_id") or research_signal.get("signal_id"),
        profile_id=gate.get("profile_id") or research_signal.get("profile_id"),
        data_snapshot_id=research_signal.get("data_snapshot_id"),
        feature_snapshot_id=research_signal.get("feature_snapshot_id"),
        now=now,
    )
