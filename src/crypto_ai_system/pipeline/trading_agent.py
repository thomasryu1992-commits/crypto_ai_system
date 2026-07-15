"""Trading agent: decision bridge -> trading cycle -> execution -> reconcile.

Respects the validation gate (``allow_new_position``) and the stage flags in
``config.settings``. The default and only currently-enabled path is paper
execution. Any live/testnet order path must be explicitly enabled *and*
carry the confirmation phrase; otherwise this agent fails closed and refuses
to run the execution stage.
"""

from __future__ import annotations

import config.settings as settings

from bridge.research_trading_bridge import run_research_trading_bridge
from crypto_ai_system.execution.order_executor import run_order_executor
from crypto_ai_system.execution.reconciler import run_reconciler
from crypto_ai_system.execution.signed_testnet_reconciliation import (
    run_signed_testnet_reconciliation,
)
from crypto_ai_system.trading.trading_cycle import run_trading_cycle

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult

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

    def execute(self, ctx: PipelineContext) -> StageResult:
        # Fail-closed stage routing. The executor's final guard is the last
        # gate before anything is signed.
        execution_stage, block_reason = resolve_execution_stage()
        if block_reason:
            return self.blocked([block_reason], fatal=True)

        allow_new_position = bool(ctx.get("allow_new_position", False))

        trading = run_trading_cycle(allow_new_position=allow_new_position)
        trade_decision = run_research_trading_bridge()
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

        # Paper position lifecycle (Path A). Distinct from order lifecycle above:
        # a position can open/close in paper without an order-intent submission.
        paper_status = trading.get("paper_result", {}).get("status") if isinstance(trading, dict) else None
        position_opened = paper_status == "POSITION_OPENED"
        position_closed = paper_status == "POSITION_CLOSED"

        outputs = {
            "execution_stage": execution_stage,
            "trading_cycle": trading,
            "trade_decision": trade_decision,
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
        }

        if not allow_new_position:
            return self.degraded(
                ["ran in no-new-position mode (validation gate closed)"],
                **outputs,
            )
        return self.ok(**outputs)
