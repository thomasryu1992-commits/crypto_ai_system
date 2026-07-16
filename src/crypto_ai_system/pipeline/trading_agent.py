"""Trading agent: decision bridge -> trading cycle -> execution -> reconcile.

Respects the validation gate (``allow_new_position``) and the stage flags in
``config.settings``. The default and only currently-enabled path is paper
execution. Any live/testnet order path must be explicitly enabled *and*
carry the confirmation phrase; otherwise this agent fails closed and refuses
to run the execution stage.
"""

from __future__ import annotations

import config.settings as settings
from config.settings import MARKET_DATA_PATH, MARKET_SNAPSHOT_PATH, TRADE_DECISION_PATH

from bridge.research_trading_bridge import run_research_trading_bridge
from core.event_log import log_event
from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.order_executor import run_order_executor
from crypto_ai_system.execution.paper_position_kernel import (
    has_open_position,
    load_open_position,
    open_from_execution,
    settle_open_position,
)
from crypto_ai_system.execution.reconciler import run_reconciler
from crypto_ai_system.execution.signed_testnet_reconciliation import (
    run_signed_testnet_reconciliation,
)
from crypto_ai_system.trading.trading_cycle import run_trading_cycle

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult


def _latest_candle() -> dict | None:
    data = read_json(MARKET_DATA_PATH, {})
    candles = data.get("candles", []) if isinstance(data, dict) else []
    if not candles:
        return None
    last = candles[-1]
    return last if isinstance(last, dict) and "high" in last and "low" in last else None


def _f(value) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


def _flag(name: str, default: bool = False) -> bool:
    return bool(getattr(settings, name, default))


def _live_requested() -> bool:
    return _flag("LIVE_TRADING_ENABLED") or _flag("ALLOW_LIVE_TRADING")


def _testnet_requested() -> bool:
    return _flag("ENABLE_TESTNET_ORDERS") or _flag("TESTNET_SIGNED_ORDER_ENABLED")


def _confirmation_present() -> bool:
    phrase = getattr(settings, "LIVE_TRADING_CONFIRMATION_PHRASE", "")
    given = getattr(settings, "LIVE_TRADING_CONFIRMATION", "")
    expected = phrase or _CONFIRMATION_PHRASE
    return bool(given) and given == expected


def resolve_execution_stage() -> tuple[str | None, str | None]:
    """Decide the execution stage from config, fail-closed.

    Returns ``(stage, block_reason)``. When ``block_reason`` is set the caller
    must refuse execution. ``stage`` is ``"paper"`` or ``"signed_testnet"``.
    """
    if _live_requested():
        return None, "live trading path is not implemented — refusing (fail-closed)"
    if _testnet_requested() and not _confirmation_present():
        return None, "testnet order flag enabled without confirmation phrase — refusing"
    if _testnet_requested() and _confirmation_present():
        return "signed_testnet", None
    return "paper", None


class TradingAgent(Agent):
    name = "trading"
    fatal_on_error = True

    def _record_strategy_outcome(self, position, settlement, ctx: PipelineContext) -> None:
        """Attribute a closed strategy-driven paper position to its strategy (S8).

        Isolated and best-effort: an attribution failure must not affect the
        trade result that already happened."""
        try:
            from crypto_ai_system.feedback.strategy_feedback_step import record_strategy_outcome

            now = ctx.cycle.started_at_utc if ctx.cycle else None
            record_strategy_outcome(
                position, settlement,
                registry_file=str(settings.STRATEGY_ATTRIBUTED_OUTCOME_REGISTRY_PATH), now=now,
            )
        except Exception as exc:  # noqa: BLE001 - attribution is best-effort, but never silent
            log_event(
                "strategy_outcome_attribution_failed",
                {"error": repr(exc)},
                severity="WARNING",
            )

    def _maybe_strategy_decision(self, ctx: PipelineContext, execution_stage: str, open_positions: int):
        """Build a strategy-driven trade decision from this cycle's router result.

        Isolated so a failure here can never break the research path: any error
        returns None and the research decision stands."""
        routing = ctx.get("strategy_routing")
        if not isinstance(routing, dict):
            return None
        try:
            from crypto_ai_system.strategy_factory.strategy_execution_bridge import (
                build_strategy_decision_for_cycle,
            )

            cycle_id = ctx.cycle.cycle_id if ctx.cycle else None
            now = ctx.cycle.started_at_utc if ctx.cycle else None
            return build_strategy_decision_for_cycle(
                routing, execution_stage=execution_stage, open_positions=open_positions,
                cycle_id=cycle_id, now=now,
            )
        except Exception:  # noqa: BLE001 - never let the drive path break research
            return None

    def execute(self, ctx: PipelineContext) -> StageResult:
        # Fail-closed stage routing. The executor's final guard is the last
        # gate before anything is signed.
        execution_stage, block_reason = resolve_execution_stage()
        if block_reason:
            return self.blocked([block_reason], fatal=True)

        allow_new_position = bool(ctx.get("allow_new_position", False))

        cfg = load_config(".")
        cycle_id = ctx.cycle.cycle_id if ctx.cycle else None
        snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
        is_paper = execution_stage == "paper"

        # 1. Settle any open paper position FIRST — SL/TP/time exit may close it
        #    and produce a CLOSED outcome before this cycle considers a new entry.
        settlement = None
        if is_paper:
            # Capture the position before settling — settle clears it, and a
            # strategy-driven close must be attributed to its strategy (S8/S9).
            open_before = load_open_position(cfg)
            settlement = settle_open_position(
                _latest_candle(),
                last_close=_f(snapshot.get("last_close")),
                timeframe=str(snapshot.get("timeframe", "1h")),
                regime=str(snapshot.get("trend_bias", "unknown")),
                cfg=cfg,
            )
            if (
                settlement is not None
                and isinstance(open_before, dict)
                and open_before.get("strategy_id")
                and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
            ):
                self._record_strategy_outcome(open_before, settlement, ctx)

        # 2. Open-position count for the gate (max_open_positions enforced there).
        open_positions = 1 if (is_paper and has_open_position(cfg)) else 0

        trading = run_trading_cycle(allow_new_position=allow_new_position)
        trade_decision = run_research_trading_bridge(execution_stage=execution_stage, open_positions=open_positions)

        # Strategy-factory drive (paper only, opt-in): when a routed candidate
        # exists this cycle, replace the research decision with a strategy-driven
        # one. It is still gated by research permission + PreOrderRiskGate inside
        # the builder, and only overrides when it produces an order-intent-eligible
        # decision — otherwise the research decision stands (fail-closed).
        strategy_drive = None
        if (
            is_paper
            and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
            and _flag("STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED")
        ):
            strategy_drive = self._maybe_strategy_decision(ctx, execution_stage, open_positions)
            if strategy_drive is not None and strategy_drive.get("allow_order_intent"):
                atomic_write_json(TRADE_DECISION_PATH, strategy_drive)
                trade_decision = strategy_drive

        order = run_order_executor(execution_stage)

        # Reconcile against the venue only when a real testnet order was
        # submitted; otherwise use the paper reconciler.
        if execution_stage == "signed_testnet" and isinstance(order, dict) and order.get(
            "external_order_submission_performed"
        ):
            reconciliation = run_signed_testnet_reconciliation()
        else:
            reconciliation = run_reconciler()

        # Derive real order lifecycle state — a non-empty result dict is NOT a
        # trade (a REJECTED/NO_ORDER result is also a dict). A trade counts only
        # when the executor actually filled (paper) or submitted (testnet).
        order = order if isinstance(order, dict) else {}
        order_status = order.get("status")
        order_filled = bool(order.get("filled"))
        order_intent_created = bool(order.get("intent", {}).get("order_intent_created")) or bool(
            order.get("order_intent_id")
        )
        order_submitted = bool(order.get("external_order_submission_performed")) or (
            order_status == "SIGNED_TESTNET_ORDER_SUBMITTED"
        )
        trade_executed = order_filled or order_status == "SIGNED_TESTNET_ORDER_SUBMITTED"

        # 3. Open a canonical paper position from a freshly filled entry (only if
        #    none is open — the gate's max_open_positions already enforces this).
        opened = None
        if is_paper and order_filled and not has_open_position(cfg):
            opened = open_from_execution(
                order,
                reconciliation if isinstance(reconciliation, dict) else {},
                cycle_id=cycle_id,
                cfg=cfg,
            )

        # Paper position lifecycle now flows through the kernel, not Path A.
        position_opened = opened is not None
        position_closed = settlement is not None

        outputs = {
            "execution_stage": execution_stage,
            "trading_cycle": trading,
            "trade_decision": trade_decision,
            "strategy_drive_decision": strategy_drive,
            "strategy_drive_active": bool(strategy_drive is not None and strategy_drive.get("allow_order_intent")),
            "order_result": order,
            "reconciliation": reconciliation,
            "trade_executed": trade_executed,
            # Lifecycle breakdown for the dashboard (not a single boolean).
            "order_status": order_status,
            "order_intent_created": order_intent_created,
            "order_submitted": order_submitted,
            "order_filled": order_filled,
            "position_opened": position_opened,
            "position_closed": position_closed,
            "position_settlement": settlement,
        }

        if not allow_new_position:
            return self.degraded(
                ["ran in no-new-position mode (validation gate closed)"],
                **outputs,
            )
        return self.ok(**outputs)
