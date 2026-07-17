"""Increment 2: turn a router entry candidate into a canonical trade decision.

The router (S7) says *which strategy fires and in which direction*; this builds
the ``TRADE_DECISION`` the existing order executor consumes, so a strategy-driven
paper entry flows through exactly the same order-intent → paper-fill → position
path as a research-driven one. Following directive §2.2, the strategy only
creates the opportunity: the entry is authorised only when the shared research
permission allows that direction *and* the PreOrderRiskGate approves. Without
both, ``allow_order_intent`` stays false (fail-closed), identical to the research
path's contract.

Exit levels come from the strategy's own ATR stop/target (the same
``cost_model`` the backtest used), and the decision carries the S8 attribution
block so the resulting order/position/outcome can be traced to the strategy.

Pure: inputs in, a decision dict out. It creates no order and evaluates no gate
itself — the caller supplies the research permission and gate result.
"""

from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.backtesting.cost_model import stop_price, target_price
from crypto_ai_system.strategy_factory.entry_strategy_router_agent import STATUS_ENTRY_CANDIDATE
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STRATEGY_TRADE_DECISION_VERSION = "strategy_trade_decision.v1"

BLOCK_NOT_A_CANDIDATE = "STRATEGY_ROUTER_NOT_A_CANDIDATE"
BLOCK_NO_PRICE = "STRATEGY_NO_ENTRY_PRICE"
BLOCK_NO_ATR = "STRATEGY_NO_ATR"
BLOCK_DIRECTION_NOT_PERMITTED = "RESEARCH_PERMISSION_DISALLOWS_STRATEGY_DIRECTION"
BLOCK_NEW_POSITION_DISALLOWED = "RESEARCH_PERMISSION_DISALLOWS_NEW_POSITION"
BLOCK_RISK_GATE = "PRE_ORDER_RISK_GATE_NOT_APPROVED"


def _f(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None  # drop NaN


def _gate_approved(gate: Mapping[str, Any]) -> bool:
    return gate.get("approved") is True or gate.get("status") in {"PASS_PAPER", "PASS_REVIEW_ONLY"}


def build_strategy_trade_decision(
    *,
    router_result: Mapping[str, Any],
    primary_spec: Mapping[str, Any],
    feature_row: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    research_permission: Mapping[str, Any],
    pre_order_risk_gate: Mapping[str, Any],
    attribution: Mapping[str, Any],
    symbol: str = "BTCUSDT",
    notional_usdt: float = 20.0,
    execution_stage: str = "paper",
    research_signal_id: str | None = None,
    profile_id: str | None = None,
    data_snapshot_id: str | None = None,
    feature_snapshot_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Build a canonical trade decision from a router candidate. Fail-closed."""
    reasons: list[str] = []
    direction = str(router_result.get("direction") or "").upper()

    if router_result.get("status") != STATUS_ENTRY_CANDIDATE or direction not in {"LONG", "SHORT"}:
        reasons.append(BLOCK_NOT_A_CANDIDATE)

    # The entry must be priced at the STRATEGY's market. The snapshot only knows
    # the runtime symbol, so its last_close is used only when the decision is for
    # that same market; otherwise the spec's own feature row (its last closed
    # bar) is the one honest price available.
    from collectors.real_market_data import to_binance_symbol

    snapshot_symbol = str(market_snapshot.get("symbol") or "")
    same_market = not snapshot_symbol or to_binance_symbol(snapshot_symbol) == to_binance_symbol(symbol)
    if same_market:
        entry = _f(market_snapshot.get("last_close")) or _f(feature_row.get("close"))
    else:
        entry = _f(feature_row.get("close"))
    if entry is None or entry <= 0:
        reasons.append(BLOCK_NO_PRICE)
    atr = _f(feature_row.get("atr"))
    if atr is None or atr <= 0:
        reasons.append(BLOCK_NO_ATR)

    # Research permission gates the strategy's direction (§2.2).
    if not research_permission.get("allow_new_position"):
        reasons.append(BLOCK_NEW_POSITION_DISALLOWED)
    if direction == "LONG" and not research_permission.get("allow_long"):
        reasons.append(BLOCK_DIRECTION_NOT_PERMITTED)
    if direction == "SHORT" and not research_permission.get("allow_short"):
        reasons.append(BLOCK_DIRECTION_NOT_PERMITTED)

    gate_approved = _gate_approved(pre_order_risk_gate)
    if not gate_approved:
        reasons.append(BLOCK_RISK_GATE)

    exit_rules = primary_spec.get("exit_rules") or {}
    stop_atr = _f(exit_rules.get("stop_atr"))
    target_atr = _f(exit_rules.get("target_atr"))

    stop_loss = take_profit = risk_reward = None
    if entry and atr and stop_atr and target_atr:
        stop_loss = round(stop_price(entry, atr, direction, stop_atr), 8)
        take_profit = round(target_price(entry, atr, direction, target_atr), 8)
        risk_reward = round(target_atr / stop_atr, 6)

    allow_order_intent = not reasons and stop_loss is not None and take_profit is not None
    if allow_order_intent:
        final_decision = f"STRATEGY_{direction}_ENTRY"
    else:
        final_decision = "STRATEGY_ENTRY_BLOCKED"

    payload: dict[str, Any] = {
        "created_at_utc": now or utc_now_canonical(),
        "strategy_trade_decision_version": STRATEGY_TRADE_DECISION_VERSION,
        "source": "strategy_factory_router",
        "symbol": symbol,
        "final_decision": final_decision,
        "direction": direction if direction in {"LONG", "SHORT"} else "NONE",
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward": risk_reward,
        "order_notional_usdt": float(notional_usdt),
        "notional_usdt": float(notional_usdt),
        "execution_stage": execution_stage,
        "decision_stage": execution_stage,
        "allow_new_position": bool(research_permission.get("allow_new_position")),
        "allow_long": bool(research_permission.get("allow_long")),
        "allow_short": bool(research_permission.get("allow_short")),
        "allow_order_intent": allow_order_intent,
        "pre_order_risk_gate_required": True,
        "pre_order_risk_gate_approved": gate_approved,
        "order_intent_block_reason": None if allow_order_intent else (reasons[0] if reasons else "STRATEGY_ENTRY_BLOCKED"),
        "block_reasons": sorted(set(reasons)),
        "order_intent_created": False,
        # Canonical lineage the order executor + paper engine require on the
        # intent. decision_id is the strategy's entry-evaluation id; the cycle's
        # research signal / profile ids carry the data lineage.
        "decision_id": attribution.get("strategy_entry_evaluation_id"),
        "research_signal_id": research_signal_id,
        "profile_id": profile_id or pre_order_risk_gate.get("profile_id"),
        "data_snapshot_id": data_snapshot_id,
        "feature_snapshot_id": feature_snapshot_id,
        "risk_gate_id": pre_order_risk_gate.get("risk_gate_id"),
        "risk_gate_status": pre_order_risk_gate.get("status"),
        "pre_order_risk_gate": dict(pre_order_risk_gate),
        # S8 attribution — rides the order intent → position → outcome.
        "strategy_id": attribution.get("strategy_id"),
        "strategy_version": attribution.get("strategy_version"),
        "strategy_generation_id": attribution.get("strategy_generation_id"),
        "strategy_rule_hash": attribution.get("strategy_rule_hash"),
        "supporting_strategy_ids": attribution.get("supporting_strategy_ids") or [],
        "matched_strategy_ids": attribution.get("matched_strategy_ids") or [],
        "strategy_entry_evaluation_id": attribution.get("strategy_entry_evaluation_id"),
        "strategy_pool_version": attribution.get("strategy_pool_version"),
        "external_order_submission_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    payload["trading_decision_agent_id"] = stable_id("strategy_trade_decision", payload, 24)
    payload["trading_decision_agent_sha256"] = sha256_json(payload)
    return payload
