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
from crypto_ai_system.strategy_factory.runtime_feature_adapter import (
    build_runtime_feature_row_for_timeframe,
)
from crypto_ai_system.strategy_factory.strategy_outcome_attribution import build_strategy_attribution
from crypto_ai_system.strategy_factory.strategy_trade_decision import build_strategy_trade_decision
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate
from crypto_ai_system.trading.trading_decision_agent import build_research_permission_decision


def _primary_spec(pool: Mapping[str, Any], strategy_id: str) -> dict | None:
    for entry in (pool.get("active_strategies") or []):
        if entry.get("strategy_id") == strategy_id and entry.get("strategy_spec"):
            return dict(entry["strategy_spec"])
    return None


def _live_gate_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """(profile, live_runtime_overrides, live_gate_config_overrides) for stage=live.

    The live profile reports approved only when the operator's live-strategy
    config is complete. The runtime overrides feed the gate the REAL live
    numbers: today's realized live P&L (L1 ledger) and today's live order count
    (L2 counter), plus the live kill switch. The config overrides arm the
    stage-execution check and the USDT-denominated caps.
    """
    from crypto_ai_system.execution.live_order_final_guard import count_today
    from crypto_ai_system.execution.live_pnl_ledger import live_daily_realized_pnl_usdt
    from crypto_ai_system.research.live_profile import get_live_profile, live_stage_fully_configured

    profile = get_live_profile()
    configured = live_stage_fully_configured()
    cap = float(getattr(settings, "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT", 0.0) or 0.0)
    ceiling = float(getattr(settings, "LIVE_STRATEGY_ABSOLUTE_MAX_NOTIONAL_USDT", 200.0) or 0.0)
    runtime_overrides = {
        "daily_pnl_usdt": live_daily_realized_pnl_usdt(),
        "daily_order_count": count_today(),
        "manual_kill_switch": bool(getattr(settings, "LIVE_STRATEGY_MANUAL_KILL_SWITCH", False)),
    }
    config_overrides = {
        # Arms the gate's STAGE_EXECUTION_DISABLED check: only a fully-configured
        # operator boundary counts as enabled.
        "live_trading_enabled": configured,
        "external_order_submission_allowed": configured,
        "max_order_notional_usdt": min(cap, ceiling) if cap > 0 else 0.0,
        "daily_loss_limit_usdt": float(getattr(settings, "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT", 0.0) or 0.0),
        "max_daily_order_count": int(getattr(settings, "LIVE_STRATEGY_MAX_DAILY_ORDER_COUNT", 0) or 0),
    }
    return profile, runtime_overrides, config_overrides


def _evaluate_strategy_risk_gate(
    direction: str,
    *,
    execution_stage: str,
    research_signal: Mapping[str, Any],
    risk: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    open_positions: int,
    eval_id: str | None,
    price: float | None = None,
) -> dict[str, Any]:
    """Evaluate the hot-path PreOrderRiskGate for the strategy's direction.

    Mirrors the research bridge's gate call but seeds the decision with the
    strategy direction. Paper gets the auto-approved paper profile; live gets the
    operator-approved live profile plus real live risk numbers; any other stage
    gets no approved profile and the gate blocks.

    ``price`` must be the STRATEGY SYMBOL's price. The market snapshot only knows
    the runtime symbol, so for a cross-symbol spec the caller passes the close
    from the spec's own feature row — gating an ETH order at BTC's price would
    make every notional and sanity check meaningless."""
    stage = str(execution_stage or "paper").lower()
    if price is None:
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
    # Paper's cap follows the multibook policy (1 single-book, else the global
    # book cap); the live stage keeps its hard cap of one position.
    if stage == "paper":
        from crypto_ai_system.execution.paper_book_kernel import paper_gate_max_open_positions

        max_open = paper_gate_max_open_positions()
    else:
        max_open = 1
    gate_config: dict[str, Any] = {
        "stage": stage,
        "max_open_positions": max_open,
        "require_profile_hash": True,
        # Same settings-derived loss limits the research bridge passes — without
        # them the gate's hardcoded defaults drift from an env-tightened
        # DAILY_MAX_LOSS_R / MAX_CONSECUTIVE_LOSSES.
        "daily_loss_limit_r": settings.DAILY_MAX_LOSS_R,
        "max_consecutive_losses": settings.MAX_CONSECUTIVE_LOSSES,
    }
    if stage == "paper":
        profile: Mapping[str, Any] = get_paper_profile()
    elif stage == "live":
        profile, runtime_overrides, config_overrides = _live_gate_inputs()
        runtime_state.update(runtime_overrides)
        gate_config.update(config_overrides)
    else:
        profile = {}
    market_state = {
        "price": price, "mark_price": price,
        "stale": bool(market_snapshot.get("is_stale", False)),
        "synthetic_flag": bool(market_snapshot.get("is_synthetic", False)),
        "fallback_flag": bool(market_snapshot.get("is_fallback", False)),
    }
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
    data_health = read_json(settings.DATA_HEALTH_PATH, {}) or {}
    market_data = read_json(settings.MARKET_DATA_PATH, {}) or {}
    candles = market_data.get("candles", []) if isinstance(market_data, dict) else []
    # The decision must carry the row on the spec's own symbol AND timeframe —
    # the pair the router matched on and the backtest scored.
    from crypto_ai_system.pipeline.strategy_routing_agent import runtime_base_timeframe

    spec_scope = primary_spec.get("symbol_scope") or []
    spec_symbol = str(spec_scope[0]) if spec_scope else None
    feature_row = build_runtime_feature_row_for_timeframe(
        str(primary_spec.get("timeframe") or runtime_base_timeframe()),
        candles,
        base_timeframe=runtime_base_timeframe(),
        symbol=spec_symbol,
        now=now,
    )

    permission = build_research_permission_decision(
        research={}, signal_payload={"signal": direction}, research_signal=research_signal
    ).to_dict()

    attribution = build_strategy_attribution(strategy_routing, primary_spec, cycle_id=cycle_id)

    # Cross-symbol specs are gated and priced at THEIR market, not the runtime
    # symbol's: the row's close is the last closed bar of the spec's own frame.
    # Compare in venue form — the snapshot says BTC-PERP where a spec says BTCUSDT.
    from collectors.real_market_data import to_binance_symbol

    runtime_symbol_venue = to_binance_symbol(str(market_snapshot.get("symbol") or ""))
    cross_symbol = bool(spec_symbol) and spec_symbol != runtime_symbol_venue
    spec_price = feature_row.get("close") if cross_symbol else None

    gate = _evaluate_strategy_risk_gate(
        direction, execution_stage=execution_stage, research_signal=research_signal,
        risk=risk, market_snapshot=market_snapshot, open_positions=open_positions,
        eval_id=attribution.get("strategy_entry_evaluation_id"),
        price=spec_price,
    )

    stage = str(execution_stage or "paper").lower()
    if stage == "live" and gate.get("approved"):
        # The live final guard requires a PERSISTED, verified stage='live' RiskGate
        # record (P0-2) — a bare approved dict on the decision is not enough.
        from crypto_ai_system.registry.risk_gate_registry import persist_risk_gate_record

        persist_risk_gate_record(gate, ttl_seconds=300)

    # The order's symbol is the STRATEGY's symbol. Same-market specs keep the
    # snapshot's canonical name (the paper engine's existing convention); only a
    # genuinely cross-symbol spec overrides it.
    if cross_symbol:
        symbol = spec_symbol
    else:
        symbol = str(market_snapshot.get("symbol") or spec_symbol or "BTCUSDT")
    if stage == "live":
        cap = float(getattr(settings, "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT", 0.0) or 0.0)
        ceiling = float(getattr(settings, "LIVE_STRATEGY_ABSOLUTE_MAX_NOTIONAL_USDT", 200.0) or 0.0)
        notional = min(cap, ceiling)
    else:
        notional = float(getattr(settings, "MAX_ORDER_NOTIONAL_USDT", 20.0))
    return build_strategy_trade_decision(
        router_result=strategy_routing, primary_spec=primary_spec, feature_row=feature_row,
        market_snapshot=market_snapshot, research_permission=permission, pre_order_risk_gate=gate,
        attribution=attribution, data_health=data_health, risk=risk,
        symbol=symbol, notional_usdt=notional,
        execution_stage=execution_stage,
        # The cycle's data lineage the paper engine requires on the intent.
        research_signal_id=research_signal.get("research_signal_id") or research_signal.get("signal_id"),
        profile_id=gate.get("profile_id") or research_signal.get("profile_id"),
        data_snapshot_id=research_signal.get("data_snapshot_id"),
        feature_snapshot_id=research_signal.get("feature_snapshot_id"),
        now=now,
    )
