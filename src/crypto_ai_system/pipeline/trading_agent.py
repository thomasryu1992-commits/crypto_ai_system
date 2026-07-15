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
from crypto_ai_system.trading.trading_cycle import run_trading_cycle

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


def _flag(name: str, default: bool = False) -> bool:
    return bool(getattr(settings, name, default))


def _live_or_testnet_requested() -> bool:
    return (
        _flag("LIVE_TRADING_ENABLED")
        or _flag("ALLOW_LIVE_TRADING")
        or _flag("ENABLE_TESTNET_ORDERS")
        or _flag("TESTNET_SIGNED_ORDER_ENABLED")
    )


def _confirmation_present() -> bool:
    phrase = getattr(settings, "LIVE_TRADING_CONFIRMATION_PHRASE", "")
    given = getattr(settings, "LIVE_TRADING_CONFIRMATION", "")
    expected = phrase or _CONFIRMATION_PHRASE
    return bool(given) and given == expected


class TradingAgent(Agent):
    name = "trading"
    fatal_on_error = True

    def execute(self, ctx: PipelineContext) -> StageResult:
        # Fail-closed safety gate: real-order paths require explicit
        # confirmation. This agent never submits a signed order today; the
        # guard exists so enabling one is a deliberate, auditable step.
        if _live_or_testnet_requested() and not _confirmation_present():
            return self.blocked(
                [
                    "live/testnet order flag enabled without confirmation phrase — "
                    "refusing to run execution (fail-closed)"
                ],
                fatal=True,
            )

        allow_new_position = bool(ctx.get("allow_new_position", False))

        trading = run_trading_cycle(allow_new_position=allow_new_position)
        trade_decision = run_research_trading_bridge()
        order = run_order_executor()
        reconciliation = run_reconciler()

        outputs = {
            "trading_cycle": trading,
            "trade_decision": trade_decision,
            "order_result": order,
            "reconciliation": reconciliation,
            # A trade is only "executed" when a new position was permitted
            # and the executor produced a result. No-new-position cycles
            # still run the executor (to reconcile open state) but do not
            # count as a placed trade.
            "trade_executed": bool(allow_new_position and order),
        }

        if not allow_new_position:
            return self.degraded(
                ["ran in no-new-position mode (validation gate closed)"],
                **outputs,
            )
        return self.ok(**outputs)
