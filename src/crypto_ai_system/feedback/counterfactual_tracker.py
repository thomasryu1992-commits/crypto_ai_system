"""Counterfactual tracker: what the gates actually cost.

The system fails closed, so most signals never become positions — a gate blocks
them. Nothing recorded *what those trades would have done*, which makes a gate
that is too conservative indistinguishable from one that is saving money: both
look identical from the outcome registry, because neither leaves a trace there.

This module shadows every blocked-but-actionable signal. It records the trade
plan the system would have taken, settles it against real candles with the same
exit math as the paper position kernel, and appends a settled counterfactual
tagged with the block reason. Per-reason expectancy over those records turns gate
calibration into an empirical question instead of a judgement call.

Purely observational: it creates no order intent, mutates no runtime setting, and
never feeds a gate decision. Its outcomes are hypothetical and live in their own
registry, so the risk guard (which reads only outcome_feedback_registry) can
never mistake one for realized P&L.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.paper_position_kernel import (
    DEFAULT_MAX_HOLD_BARS,
    MAX_HOLD_BARS,
    settle_trade_plan,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.research.active_research_signal import LONG_SCENARIOS, SHORT_SCENARIOS
from crypto_ai_system.trading.trading_decision_agent import build_price_structure_decision
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

COUNTERFACTUAL_TRACKER_VERSION = "counterfactual_tracker.v1"
COUNTERFACTUAL_OUTCOME_REGISTRY_NAME = "counterfactual_outcome_registry"

# This module observes; it never trades.
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
ORDER_INTENT_CREATED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
GATE_DECISIONS_INFLUENCED_BY_THIS_MODULE = False

# A signal blocked by a persistent condition (a daily loss limit, say) re-fires
# every cycle. The cap bounds the shadow book so a stuck gate cannot grow it
# without limit.
MAX_OPEN_COUNTERFACTUALS = 50

MISSED_OPPORTUNITY = "MISSED_OPPORTUNITY"
AVOIDED_LOSS = "AVOIDED_LOSS"
NEUTRAL_BLOCK = "NEUTRAL_BLOCK"


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _book_path(cfg: AppConfig) -> Path:
    return _latest_path(cfg, "counterfactual_positions.json")


def load_open_counterfactuals(cfg: AppConfig | None = None) -> list[dict[str, Any]]:
    cfg = cfg or load_config(".")
    book = read_json(_book_path(cfg), None)
    if not isinstance(book, dict):
        return []
    rows = book.get("positions")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("status") == "OPEN"]


def _save_book(cfg: AppConfig, rows: list[dict[str, Any]]) -> None:
    atomic_write_json(
        _book_path(cfg),
        {
            "counterfactual_tracker_version": COUNTERFACTUAL_TRACKER_VERSION,
            "updated_at_utc": utc_now_canonical(),
            "open_count": len(rows),
            "positions": rows,
        },
    )


def _block_context(trade_decision: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    """Return (block_stage, block_reason, block_reasons) for a decision not taken.

    The PreOrderRiskGate is the more specific authority when it blocked, so its
    status wins over the trading decision's coarser final_decision."""
    gate = dict(trade_decision.get("pre_order_risk_gate") or {})
    gate_status = str(gate.get("status") or "")
    if gate.get("approved") is not True and gate_status.startswith("BLOCK_"):
        reasons = sorted({str(r) for r in (gate.get("block_reasons") or []) if str(r)})
        return "pre_order_risk_gate", gate_status, reasons
    final_decision = str(trade_decision.get("final_decision") or "UNKNOWN")
    reasons = sorted({str(r) for r in (trade_decision.get("reasons") or []) if str(r)})
    return "trading_decision", final_decision, reasons


def _direction_from_scenario(research_signal: Mapping[str, Any]) -> str:
    """The research's directional view, read straight from the scenario.

    Every downstream field that carries direction is permission-derived, so a
    timing or data block collapses them all to FLAT/NONE. The scenario is the one
    place the view survives the block — and a block that suppressed a real
    directional view is exactly what this module exists to measure."""
    scenario = str(research_signal.get("scenario") or "")
    if scenario in LONG_SCENARIOS:
        return "LONG"
    if scenario in SHORT_SCENARIOS:
        return "SHORT"
    return "NONE"


def _intended_direction(
    trade_decision: Mapping[str, Any], research_signal: Mapping[str, Any]
) -> str:
    """The side the system wanted, not the side the blocked decision reports.

    build_trading_decision forces direction='NONE' on every block and the
    permission gate rewrites the signal's side to FLAT, so neither can answer
    this once something blocked. Falls back through the chain to the scenario,
    which no gate rewrites. Returns NONE only when the research genuinely had no
    directional view — there is nothing to miss in that case."""
    sources = (dict(trade_decision.get("trading_signal") or {}), dict(research_signal or {}))
    for source in sources:
        for key in ("signal", "side", "entry_side"):
            value = str(source.get(key) or "").upper()
            if value in {"LONG", "SHORT"}:
                return value
    return _direction_from_scenario(research_signal or {})


def _coherent(direction: str, entry: float, stop_loss: float, take_profit: float) -> bool:
    if direction == "LONG":
        return stop_loss < entry < take_profit
    return take_profit < entry < stop_loss


def build_counterfactual_plan(
    trade_decision: Mapping[str, Any],
    *,
    market_snapshot: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any] | None:
    """The trade the system would have taken had nothing blocked it.

    Returns None when there was no actionable setup to miss — no direction, no
    usable price structure, or an incoherent plan. Entry/SL/TP are recomputed
    from the intended direction rather than read off the blocked decision, whose
    price structure was built against direction='NONE'."""
    market_snapshot = dict(market_snapshot or {})
    research_signal = dict(research_signal or {})
    direction = _intended_direction(trade_decision, research_signal)
    if direction not in {"LONG", "SHORT"}:
        return None

    signal_payload = {**dict(trade_decision.get("trading_signal") or {}), "signal": direction}
    structure = build_price_structure_decision(
        signal_payload=signal_payload,
        market_snapshot=market_snapshot,
        research_signal=research_signal,
    )
    entry, stop_loss, take_profit = structure.entry, structure.stop_loss, structure.take_profit
    if entry is None or stop_loss is None or take_profit is None:
        return None
    if not _coherent(direction, entry, stop_loss, take_profit):
        return None
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return None

    gate = dict(trade_decision.get("pre_order_risk_gate") or {})
    block_stage, block_reason, block_reasons = _block_context(trade_decision)
    plan = {
        "counterfactual_tracker_version": COUNTERFACTUAL_TRACKER_VERSION,
        "status": "OPEN",
        "symbol": trade_decision.get("symbol") or market_snapshot.get("symbol"),
        "timeframe": str(market_snapshot.get("timeframe") or "1h"),
        "direction": direction,
        "entry_price": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk": risk,
        "risk_reward": structure.risk_reward,
        "holding_candles": 0,
        "intrabar_policy": "pessimistic_sl_first",
        "opened_at_utc": utc_now_canonical(),
        "cycle_id": cycle_id,
        "block_stage": block_stage,
        "block_reason": block_reason,
        "block_reasons": block_reasons,
        "final_decision": str(trade_decision.get("final_decision") or "UNKNOWN"),
        "risk_gate_status": gate.get("status"),
        "research_signal_id": trade_decision.get("research_signal_id")
        or research_signal.get("research_signal_id"),
        "decision_id": trade_decision.get("decision_id"),
        "profile_id": trade_decision.get("profile_id") or research_signal.get("profile_id"),
        "data_snapshot_id": trade_decision.get("data_snapshot_id"),
        "feature_snapshot_id": trade_decision.get("feature_snapshot_id"),
        "risk_gate_id": trade_decision.get("risk_gate_id"),
        "strategy_id": trade_decision.get("strategy_id"),
    }
    # Content-addressed and deliberately excluding cycle_id/opened_at: the same
    # setup blocked for the same reason is one shadow trade, however many cycles
    # it re-fires across.
    plan["counterfactual_id"] = stable_id(
        "counterfactual",
        {
            "research_signal_id": plan["research_signal_id"],
            "direction": direction,
            "entry_price": entry,
            "block_reason": block_reason,
        },
        24,
    )
    return plan


def record_blocked_signal(
    trade_decision: Mapping[str, Any],
    *,
    market_snapshot: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
    cycle_id: str | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any] | None:
    """Open a shadow position for a signal the system wanted but did not take.

    Returns the recorded plan, or None when there was nothing to record (no
    actionable setup, already shadowed, or the book is full)."""
    cfg = cfg or load_config(".")
    plan = build_counterfactual_plan(
        trade_decision,
        market_snapshot=market_snapshot,
        research_signal=research_signal,
        cycle_id=cycle_id,
    )
    if plan is None:
        return None
    rows = load_open_counterfactuals(cfg)
    if any(row.get("counterfactual_id") == plan["counterfactual_id"] for row in rows):
        return None
    if len(rows) >= MAX_OPEN_COUNTERFACTUALS:
        return None
    rows.append(plan)
    _save_book(cfg, rows)
    return plan


def classify_counterfactual(result_r: float) -> str:
    """A blocked trade that would have won is a cost; one that would have lost is
    the gate earning its keep."""
    if result_r > 0:
        return MISSED_OPPORTUNITY
    if result_r < 0:
        return AVOIDED_LOSS
    return NEUTRAL_BLOCK


def build_counterfactual_outcome_record(
    plan: Mapping[str, Any],
    *,
    close_reason: str,
    exit_price: float | None,
    result_r: float,
    regime: str | None = None,
) -> dict[str, Any]:
    record = {
        "counterfactual_outcome_version": COUNTERFACTUAL_TRACKER_VERSION,
        "counterfactual_id": plan.get("counterfactual_id"),
        "outcome_closed": True,
        # No order ever existed. This must never be read as realized P&L.
        "hypothetical": True,
        "classification": classify_counterfactual(result_r),
        "result_R": round(float(result_r), 8),
        "close_reason": close_reason,
        "exit_price": exit_price,
        "holding_candles": int(plan.get("holding_candles", 0) or 0),
        "regime": regime or "unknown",
        "symbol": plan.get("symbol"),
        "timeframe": plan.get("timeframe"),
        "direction": plan.get("direction"),
        "entry_price": plan.get("entry_price"),
        "stop_loss": plan.get("stop_loss"),
        "take_profit": plan.get("take_profit"),
        "risk": plan.get("risk"),
        "risk_reward": plan.get("risk_reward"),
        "block_stage": plan.get("block_stage"),
        "block_reason": plan.get("block_reason"),
        "block_reasons": plan.get("block_reasons") or [],
        "final_decision": plan.get("final_decision"),
        "risk_gate_status": plan.get("risk_gate_status"),
        "research_signal_id": plan.get("research_signal_id"),
        "decision_id": plan.get("decision_id"),
        "profile_id": plan.get("profile_id"),
        "data_snapshot_id": plan.get("data_snapshot_id"),
        "feature_snapshot_id": plan.get("feature_snapshot_id"),
        "risk_gate_id": plan.get("risk_gate_id"),
        "strategy_id": plan.get("strategy_id"),
        "cycle_id": plan.get("cycle_id"),
        "opened_at_utc": plan.get("opened_at_utc"),
        "closed_at_utc": utc_now_canonical(),
        "order_intent_created": ORDER_INTENT_CREATED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "gate_decisions_influenced_by_this_module": GATE_DECISIONS_INFLUENCED_BY_THIS_MODULE,
        "created_at_utc": utc_now_canonical(),
    }
    record["counterfactual_outcome_record_sha256"] = sha256_json(record)
    return record


def persist_counterfactual_outcome(
    cfg: AppConfig,
    plan: Mapping[str, Any],
    *,
    close_reason: str,
    exit_price: float | None,
    result_r: float,
    regime: str | None = None,
) -> dict[str, Any]:
    record = build_counterfactual_outcome_record(
        plan,
        close_reason=close_reason,
        exit_price=exit_price,
        result_r=result_r,
        regime=regime,
    )
    return append_registry_record(
        registry_path(cfg, COUNTERFACTUAL_OUTCOME_REGISTRY_NAME),
        record,
        registry_name=COUNTERFACTUAL_OUTCOME_REGISTRY_NAME,
        id_field="counterfactual_outcome_id",
        hash_field="counterfactual_outcome_record_sha256",
        id_prefix="counterfactual_outcome",
    )


def settle_counterfactuals(
    candle: Mapping[str, Any] | None,
    *,
    last_close: float | None = None,
    timeframe: str = "1h",
    regime: str | None = None,
    cfg: AppConfig | None = None,
) -> list[dict[str, Any]]:
    """Advance every open shadow position by one candle; persist the ones that exit.

    Uses the paper kernel's settle math so a shadow result_R means exactly what a
    real paper result_R means."""
    cfg = cfg or load_config(".")
    rows = load_open_counterfactuals(cfg)
    if not rows:
        return []

    still_open: list[dict[str, Any]] = []
    settled: list[dict[str, Any]] = []
    for plan in rows:
        max_hold = MAX_HOLD_BARS.get(
            str(plan.get("timeframe") or timeframe), DEFAULT_MAX_HOLD_BARS
        )
        reason, exit_price, result_r = settle_trade_plan(plan, candle, last_close, max_hold, False)
        if reason is None:
            plan["last_seen_price"] = last_close
            still_open.append(plan)
            continue
        settled.append(
            persist_counterfactual_outcome(
                cfg,
                plan,
                close_reason=reason,
                exit_price=exit_price,
                result_r=float(result_r),
                regime=regime,
            )
        )
    _save_book(cfg, still_open)
    return settled
