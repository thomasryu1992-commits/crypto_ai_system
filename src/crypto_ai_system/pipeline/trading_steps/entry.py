"""Single-book entry step + isolated strategy-drive decision builders (M4).

The entry chain is: research bridge decision -> optional strategy-drive
override (still gated by research permission + PreOrderRiskGate inside the
builder; only an order-intent-eligible decision overrides, otherwise the
research decision stands, fail-closed) -> order executor -> reconciliation
selection (venue reconciliation only when a real external order was
submitted).

``executor`` / ``reconciler`` / ``persist`` are injected by the agent from its
own module surface so existing monkeypatches keep working; they default to
nothing here on purpose — the agent decides the wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from config.settings import TRADE_DECISION_PATH

from bridge.research_trading_bridge import run_research_trading_bridge
from crypto_ai_system.pipeline.contracts import ValidationVerdict
from crypto_ai_system.pipeline.trading_steps.context import CycleInputs
from crypto_ai_system.pipeline.trading_steps.stage_router import _flag


@dataclass(frozen=True)
class EntryOutcome:
    trade_decision: dict
    strategy_drive: dict | None
    order: dict
    reconciliation: dict
    externally_submitted: bool


def build_drive_decision(
    routing: Mapping[str, Any] | None,
    verdict: ValidationVerdict,
    *,
    execution_stage: str,
    open_positions: int,
    cycle_id: str | None,
    now: str | None,
) -> dict | None:
    """Build a strategy-driven trade decision from this cycle's router result.

    Isolated so a failure here can never break the research path: any error
    returns None and the research decision stands."""
    if not isinstance(routing, dict):
        return None
    try:
        from crypto_ai_system.strategy_factory.strategy_execution_bridge import (
            build_strategy_decision_for_cycle,
        )

        return build_strategy_decision_for_cycle(
            routing, execution_stage=execution_stage, open_positions=open_positions,
            data_health=verdict.data_health, risk=verdict.risk_status,
            cycle_id=cycle_id, now=now,
        )
    except Exception:  # noqa: BLE001 - never let the drive path break research
        return None


def build_candidate_decision(
    routing: Mapping[str, Any] | None,
    verdict: ValidationVerdict,
    candidate: Mapping[str, Any],
    *,
    execution_stage: str,
    open_positions: int,
    cycle_id: str | None,
    now: str | None,
) -> dict | None:
    """A strategy decision for ONE ranked candidate (multibook entry walk).

    The decision builder reads the routing's primary_* fields, so the
    candidate is presented as the primary of a shallow routing copy.
    Isolated like build_drive_decision: any failure returns None."""
    if not isinstance(routing, dict):
        return None
    candidate_routing = {
        **routing,
        "primary_strategy_id": candidate.get("strategy_id"),
        "primary_strategy_rule_hash": candidate.get("strategy_rule_hash"),
        "direction": candidate.get("direction"),
        "symbol": candidate.get("symbol"),
    }
    return build_drive_decision(
        candidate_routing, verdict, execution_stage=execution_stage,
        open_positions=open_positions, cycle_id=cycle_id, now=now,
    )


def run_single_entry(
    inputs: CycleInputs,
    *,
    open_positions: int,
    executor: Callable[[str], dict],
    reconciler: Callable[[], dict],
    persist: Callable[..., None],
) -> EntryOutcome:
    """The single-book entry chain, verbatim from the pre-split agent."""
    verdict = inputs.verdict
    trade_decision = run_research_trading_bridge(
        execution_stage=inputs.stage, open_positions=open_positions,
        data_health=verdict.data_health, risk=verdict.risk_status,
    )

    # Strategy-factory drive (paper or live, opt-in): when a routed candidate
    # exists this cycle, replace the research decision with a strategy-driven
    # one. On the live stage the L2 final guard additionally requires the
    # persisted stage='live' RiskGate record before anything is signed.
    strategy_drive = None
    drive_eligible = (
        (inputs.is_paper or inputs.is_live)
        and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
        and _flag("STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED")
    )
    if drive_eligible:
        strategy_drive = build_drive_decision(
            inputs.routing, verdict, execution_stage=inputs.stage,
            open_positions=open_positions, cycle_id=inputs.cycle_id, now=inputs.now,
        )
        if strategy_drive is not None and strategy_drive.get("allow_order_intent"):
            persist(TRADE_DECISION_PATH, strategy_drive)
            trade_decision = strategy_drive

    order = executor(inputs.stage)
    order = order if isinstance(order, dict) else {}

    # Reconcile against the venue only when a real external order was
    # submitted; otherwise use the paper reconciler.
    externally_submitted = bool(order.get("external_order_submission_performed"))
    if inputs.stage == "signed_testnet" and externally_submitted:
        from crypto_ai_system.execution.signed_testnet_reconciliation import (
            run_signed_testnet_reconciliation,
        )

        reconciliation = run_signed_testnet_reconciliation()
    elif inputs.stage == "live" and externally_submitted:
        from crypto_ai_system.execution.live_strategy_execution import (
            run_live_strategy_reconciliation,
        )

        reconciliation = run_live_strategy_reconciliation()
    else:
        reconciliation = reconciler()

    return EntryOutcome(
        trade_decision=trade_decision,
        strategy_drive=strategy_drive,
        order=order,
        reconciliation=reconciliation if isinstance(reconciliation, dict) else {},
        externally_submitted=externally_submitted,
    )
