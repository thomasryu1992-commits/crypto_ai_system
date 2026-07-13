from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from crypto_ai_system.trading.order_id_chain import ORDER_ID_CHAIN_VERSION
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

TRADING_DECISION_AGENT_VERSION = "step292_trading_decision_agent_refactor_v1"
TRADING_DECISION_MODE = "TRADING_DECISION_REVIEW_ONLY_NO_ORDER_INTENT"
ORDER_INTENT_CREATION_ENABLED_BY_AGENT = False
ORDER_ROUTING_ENABLED_BY_AGENT = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_AGENT = False

ORDER_INTENT_BLOCKED_UNTIL_PRE_ORDER_RISK_GATE = "PRE_ORDER_RISK_GATE_REQUIRED_BEFORE_ORDER_INTENT"


@dataclass(frozen=True)
class PriceStructureDecision:
    """Price-structure-only trade setup preview.

    This object is audit evidence. It does not grant order permission. Price
    structure may identify direction/entry/SL/TP/RR, while ResearchSignal and the
    PreOrderRiskGate remain separate authorities.
    """

    direction: str
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    invalidation_conditions: list[str] = field(default_factory=list)
    source: str = "price_structure"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchPermissionDecision:
    permission_result: str
    allow_long: bool
    allow_short: bool
    allow_new_position: bool
    risk_level: str
    position_size_multiplier: float
    block_reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    source: str = "research_signal_permission"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float_or_none(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        parsed = float(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _side_from_signal(signal_payload: Mapping[str, Any]) -> str:
    side = str(signal_payload.get("signal") or signal_payload.get("side") or signal_payload.get("entry_side") or "NONE").upper()
    return side if side in {"LONG", "SHORT"} else "NONE"


def _symbol(research: Mapping[str, Any], market_snapshot: Mapping[str, Any], research_signal: Mapping[str, Any]) -> str:
    return str(
        market_snapshot.get("canonical_symbol")
        or market_snapshot.get("symbol")
        or research_signal.get("canonical_symbol")
        or research_signal.get("symbol")
        or research.get("symbol")
        or "BTCUSDT"
    )


def _price_from_market(market_snapshot: Mapping[str, Any], research_signal: Mapping[str, Any]) -> float | None:
    for key in ("last_close", "close", "price", "last_price", "mark_price"):
        price = _float_or_none(market_snapshot.get(key))
        if price is not None:
            return price
    for key in ("entry", "entry_price", "last_close", "close"):
        price = _float_or_none(research_signal.get(key))
        if price is not None:
            return price
    return None


def _atr_from_market(market_snapshot: Mapping[str, Any], research_signal: Mapping[str, Any]) -> float | None:
    for key in ("atr", "atr_14", "volatility_atr", "average_true_range"):
        atr = _float_or_none(market_snapshot.get(key))
        if atr is not None:
            return atr
    for key in ("atr", "atr_14", "volatility_atr"):
        atr = _float_or_none(research_signal.get(key))
        if atr is not None:
            return atr
    return None


def _rr(entry: float | None, stop_loss: float | None, take_profit: float | None) -> float | None:
    if entry is None or stop_loss is None or take_profit is None:
        return None
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    if risk <= 0:
        return None
    return round(reward / risk, 6)


def build_price_structure_decision(
    *,
    signal_payload: Mapping[str, Any] | None = None,
    market_snapshot: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
) -> PriceStructureDecision:
    signal_payload = dict(signal_payload or {})
    market_snapshot = dict(market_snapshot or {})
    research_signal = dict(research_signal or {})

    direction = _side_from_signal(signal_payload)
    entry = _float_or_none(signal_payload.get("entry")) or _float_or_none(signal_payload.get("entry_price")) or _price_from_market(market_snapshot, research_signal)
    stop_loss = _float_or_none(signal_payload.get("stop_loss")) or _float_or_none(research_signal.get("stop_loss"))
    take_profit = _float_or_none(signal_payload.get("take_profit")) or _float_or_none(research_signal.get("take_profit"))
    invalidations = _as_list(signal_payload.get("invalidation_conditions")) + _as_list(research_signal.get("invalidation_conditions"))

    # Step292 uses a deterministic review-only price-structure preview when a
    # directional setup exists but explicit SL/TP are not yet available. This is
    # not execution permission; it is just an auditable setup candidate.
    if direction in {"LONG", "SHORT"} and entry is not None:
        atr = _atr_from_market(market_snapshot, research_signal)
        if atr is None:
            atr = max(entry * 0.005, 1e-9)
            invalidations.append("ATR_NOT_AVAILABLE_USED_REVIEW_ONLY_PERCENT_DISTANCE")
        if stop_loss is None:
            stop_loss = entry - atr if direction == "LONG" else entry + atr
        if take_profit is None:
            take_profit = entry + (atr * 2.0) if direction == "LONG" else entry - (atr * 2.0)
        invalidations.append("PRICE_STRUCTURE_PREVIEW_REQUIRES_PRE_ORDER_RISK_GATE_BEFORE_ORDER_INTENT")
    else:
        invalidations.append("NO_DIRECTIONAL_PRICE_STRUCTURE")

    return PriceStructureDecision(
        direction=direction,
        entry=round(entry, 8) if entry is not None else None,
        stop_loss=round(stop_loss, 8) if stop_loss is not None else None,
        take_profit=round(take_profit, 8) if take_profit is not None else None,
        risk_reward=_rr(entry, stop_loss, take_profit),
        invalidation_conditions=sorted(set(invalidations)),
    )


def build_research_permission_decision(
    *,
    research: Mapping[str, Any] | None = None,
    signal_payload: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
) -> ResearchPermissionDecision:
    research = dict(research or {})
    signal_payload = dict(signal_payload or {})
    research_signal = dict(research_signal or {})
    trade_permission = research_signal.get("trade_permission") if isinstance(research_signal.get("trade_permission"), Mapping) else {}
    direction = _side_from_signal(signal_payload)
    allow_long = bool(signal_payload.get("allow_long", trade_permission.get("allow_long", research.get("allow_long", direction == "LONG"))))
    allow_short = bool(signal_payload.get("allow_short", trade_permission.get("allow_short", research.get("allow_short", direction == "SHORT"))))
    allow_new = bool(signal_payload.get("allow_new_position", trade_permission.get("allow_new_position", research.get("allow_new_position", False))))
    risk_level = str(signal_payload.get("risk_level") or trade_permission.get("risk_level") or research.get("risk_level") or "blocked").lower()
    if risk_level not in {"normal", "reduced", "blocked"}:
        risk_level = "blocked"
    blocks = _as_list(signal_payload.get("block_reasons")) + _as_list(trade_permission.get("block_reasons")) + _as_list(research.get("block_reasons"))
    warnings = _as_list(signal_payload.get("risk_warnings")) + _as_list(trade_permission.get("risk_warnings"))
    if not allow_new:
        blocks.append("RESEARCH_PERMISSION_DISALLOWS_NEW_POSITION")
    if direction == "LONG" and not allow_long:
        blocks.append("RESEARCH_PERMISSION_DISALLOWS_LONG")
    if direction == "SHORT" and not allow_short:
        blocks.append("RESEARCH_PERMISSION_DISALLOWS_SHORT")
    if direction == "NONE":
        blocks.append("RESEARCH_PERMISSION_NO_DIRECTION")
    if risk_level == "blocked":
        blocks.append("RESEARCH_PERMISSION_RISK_LEVEL_BLOCKED")

    permission_result = str(research_signal.get("permission_result") or signal_payload.get("permission_result") or "review_only")
    return ResearchPermissionDecision(
        permission_result=permission_result,
        allow_long=allow_long,
        allow_short=allow_short,
        allow_new_position=bool(allow_new and risk_level != "blocked" and not blocks),
        risk_level="blocked" if blocks else risk_level,
        position_size_multiplier=float(signal_payload.get("position_size_multiplier") or trade_permission.get("position_size_multiplier") or (0.0 if blocks else 1.0)),
        block_reasons=sorted(set(blocks)),
        risk_warnings=sorted(set(warnings)),
    )


def _base_block(
    *,
    final_decision: str,
    direction: str = "NONE",
    confidence: int = 0,
    reasons: list[str] | None = None,
    research: Mapping[str, Any] | None = None,
    signal_payload: Mapping[str, Any] | None = None,
    data_health: Mapping[str, Any] | None = None,
    risk: Mapping[str, Any] | None = None,
    market_snapshot: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    research = dict(research or {})
    signal_payload = dict(signal_payload or {})
    data_health = dict(data_health or {})
    risk = dict(risk or {})
    market_snapshot = dict(market_snapshot or {})
    research_signal = dict(research_signal or {})
    price_structure = build_price_structure_decision(signal_payload={**signal_payload, "signal": direction}, market_snapshot=market_snapshot, research_signal=research_signal)
    permission = build_research_permission_decision(research=research, signal_payload={**signal_payload, "signal": direction}, research_signal=research_signal)
    payload = {
        "created_at_utc": utc_now_canonical(),
        "trading_decision_agent_version": TRADING_DECISION_AGENT_VERSION,
        "trading_decision_mode": TRADING_DECISION_MODE,
        "chain_version": ORDER_ID_CHAIN_VERSION,
        "symbol": _symbol(research, market_snapshot, research_signal),
        "final_decision": final_decision,
        "direction": direction,
        "confidence": int(confidence or 0),
        "reasons": sorted(set(reasons or [])),
        "price_structure": price_structure.to_dict(),
        "research_permission": permission.to_dict(),
        "entry": price_structure.entry,
        "stop_loss": price_structure.stop_loss,
        "take_profit": price_structure.take_profit,
        "risk_reward": price_structure.risk_reward,
        "permission_result": permission.permission_result,
        "allow_long": False,
        "allow_short": False,
        "allow_new_position": False,
        "allow_order_intent": False,
        "pre_order_risk_gate_required": True,
        "pre_order_risk_gate_approved": False,
        "order_intent_blocked_until_pre_order_risk_gate": True,
        "order_intent_block_reason": ORDER_INTENT_BLOCKED_UNTIL_PRE_ORDER_RISK_GATE,
        "order_intent_created": False,
        "trade_approved": False,
        "order_execution_enabled_by_this_agent": ORDER_INTENT_CREATION_ENABLED_BY_AGENT,
        "order_routing_enabled_by_this_agent": ORDER_ROUTING_ENABLED_BY_AGENT,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_AGENT,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    payload["trading_decision_agent_id"] = stable_id("trading_decision", payload, 24)
    payload["trading_decision_agent_sha256"] = sha256_json(payload)
    return payload


def build_trading_decision(
    *,
    research: Mapping[str, Any] | None = None,
    trading: Mapping[str, Any] | None = None,
    data_health: Mapping[str, Any] | None = None,
    risk: Mapping[str, Any] | None = None,
    market_snapshot: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
    pre_order_risk_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Step292 trading decision candidate without creating order intent.

    Price structure provides entry/SL/TP, ResearchSignal provides directional
    permission, and PreOrderRiskGate is the only component allowed to unlock
    order-intent creation in later stages. When no risk-gate approval is passed,
    this function always returns allow_order_intent=False.
    """
    research = dict(research or {})
    trading = dict(trading or {})
    data_health = dict(data_health or {})
    risk = dict(risk or {})
    market_snapshot = dict(market_snapshot or {})
    research_signal = dict(research_signal or {})
    pre_order_risk_gate = dict(pre_order_risk_gate or {})
    signal_payload = dict(trading.get("trading_signal") or trading.get("signal") or {})
    direction = _side_from_signal(signal_payload)
    confidence = int(signal_payload.get("confidence", 0) or 0)

    if not data_health.get("allow_trading", False):
        return _base_block(
            final_decision="BLOCK_DATA_HEALTH",
            direction="NONE",
            confidence=0,
            reasons=["data_health_disallows_trading"] + _as_list(data_health.get("problems")),
            research=research,
            signal_payload=signal_payload,
            data_health=data_health,
            risk=risk,
            market_snapshot=market_snapshot,
            research_signal=research_signal,
        )
    if data_health.get("is_synthetic") or data_health.get("is_fallback"):
        return _base_block(
            final_decision="BLOCK_SYNTHETIC_DATA",
            direction="NONE",
            confidence=0,
            reasons=["synthetic_or_fallback_data_blocked"],
            research=research,
            signal_payload=signal_payload,
            data_health=data_health,
            risk=risk,
            market_snapshot=market_snapshot,
            research_signal=research_signal,
        )
    if not risk.get("allow_new_position", False):
        return _base_block(
            final_decision="BLOCK_RISK",
            direction="NONE",
            confidence=0,
            reasons=["risk_guard_disallows_new_position"] + _as_list(risk.get("problems")),
            research=research,
            signal_payload=signal_payload,
            data_health=data_health,
            risk=risk,
            market_snapshot=market_snapshot,
            research_signal=research_signal,
        )

    scenario = research.get("scenario")
    timing = research.get("signal_timing")
    if direction == "NONE":
        if scenario in {"Bullish", "Constructive"}:
            final_decision, reasons = "WATCH_LONG", ["research_constructive_but_no_trading_signal"]
        elif scenario == "Bearish":
            final_decision, reasons = "WATCH_SHORT", ["research_bearish_but_no_trading_signal"]
        else:
            final_decision, reasons = "NO_ACTION", ["no_trading_signal"]
        return _base_block(
            final_decision=final_decision,
            direction="NONE",
            confidence=confidence,
            reasons=reasons,
            research=research,
            signal_payload=signal_payload,
            data_health=data_health,
            risk=risk,
            market_snapshot=market_snapshot,
            research_signal=research_signal,
        )

    if timing in {"Late", "Data-Blocked"}:
        return _base_block(
            final_decision="BLOCK_LATE_OR_DATA_BLOCKED",
            direction="NONE",
            confidence=confidence,
            reasons=[f"signal_timing_{timing}"],
            research=research,
            signal_payload=signal_payload,
            data_health=data_health,
            risk=risk,
            market_snapshot=market_snapshot,
            research_signal=research_signal,
        )

    research_permission = build_research_permission_decision(research=research, signal_payload=signal_payload, research_signal=research_signal)
    aligned_long = direction == "LONG" and bool(research.get("allow_long")) and research_permission.allow_long
    aligned_short = direction == "SHORT" and bool(research.get("allow_short")) and research_permission.allow_short
    if not (aligned_long or aligned_short):
        return _base_block(
            final_decision="BLOCK_CONFLICTING_SIGNAL",
            direction="NONE",
            confidence=confidence,
            reasons=[f"signal_{direction}_conflicts_with_research_bias_{research.get('research_bias')}"] + research_permission.block_reasons,
            research=research,
            signal_payload=signal_payload,
            data_health=data_health,
            risk=risk,
            market_snapshot=market_snapshot,
            research_signal=research_signal,
        )

    price_structure = build_price_structure_decision(signal_payload=signal_payload, market_snapshot=market_snapshot, research_signal=research_signal)
    if price_structure.entry is None or price_structure.stop_loss is None or price_structure.take_profit is None or price_structure.risk_reward is None:
        return _base_block(
            final_decision="BLOCK_PRICE_STRUCTURE_INCOMPLETE",
            direction="NONE",
            confidence=confidence,
            reasons=["price_structure_missing_entry_sl_tp_rr"],
            research=research,
            signal_payload=signal_payload,
            data_health=data_health,
            risk=risk,
            market_snapshot=market_snapshot,
            research_signal=research_signal,
        )

    risk_gate_approved = bool(pre_order_risk_gate.get("approved") is True or pre_order_risk_gate.get("status") in {"PASS_PAPER", "PASS_REVIEW_ONLY"})
    candidate_direction = direction
    final_decision = f"REVIEW_ONLY_{candidate_direction}_CANDIDATE"
    reasons = [f"price_structure_and_research_permission_aligned_{candidate_direction.lower()}"]
    if not risk_gate_approved:
        reasons.append(ORDER_INTENT_BLOCKED_UNTIL_PRE_ORDER_RISK_GATE)
    allow_order_intent = bool(risk_gate_approved and ORDER_INTENT_CREATION_ENABLED_BY_AGENT)

    payload = {
        "created_at_utc": utc_now_canonical(),
        "trading_decision_agent_version": TRADING_DECISION_AGENT_VERSION,
        "trading_decision_mode": TRADING_DECISION_MODE,
        "chain_version": ORDER_ID_CHAIN_VERSION,
        "symbol": _symbol(research, market_snapshot, research_signal),
        "final_decision": final_decision,
        "direction": candidate_direction,
        "confidence": confidence,
        "reasons": reasons,
        "price_structure": price_structure.to_dict(),
        "research_permission": research_permission.to_dict(),
        "entry": price_structure.entry,
        "stop_loss": price_structure.stop_loss,
        "take_profit": price_structure.take_profit,
        "risk_reward": price_structure.risk_reward,
        "permission_result": research_permission.permission_result,
        "allow_long": bool(candidate_direction == "LONG" and research_permission.allow_long),
        "allow_short": bool(candidate_direction == "SHORT" and research_permission.allow_short),
        "allow_new_position": bool(research_permission.allow_new_position),
        "allow_order_intent": allow_order_intent,
        "pre_order_risk_gate_required": True,
        "pre_order_risk_gate_approved": risk_gate_approved,
        "order_intent_blocked_until_pre_order_risk_gate": not allow_order_intent,
        "order_intent_block_reason": None if allow_order_intent else ORDER_INTENT_BLOCKED_UNTIL_PRE_ORDER_RISK_GATE,
        "order_intent_created": False,
        "trade_approved": False,
        "order_execution_enabled_by_this_agent": ORDER_INTENT_CREATION_ENABLED_BY_AGENT,
        "order_routing_enabled_by_this_agent": ORDER_ROUTING_ENABLED_BY_AGENT,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_AGENT,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    payload["trading_decision_agent_id"] = stable_id("trading_decision", payload, 24)
    payload["trading_decision_agent_sha256"] = sha256_json(payload)
    return payload
