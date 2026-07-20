"""Trading agent: decision bridge -> trading cycle -> execution -> reconcile.

Respects the validation gate (``allow_new_position``) and the stage flags in
``config.settings``. The default and only currently-enabled path is paper
execution. Any live/testnet order path must be explicitly enabled *and*
carry the confirmation phrase; otherwise this agent fails closed and refuses
to run the execution stage.
"""

from __future__ import annotations

import config.settings as settings
from config.settings import (
    MARKET_DATA_PATH,
    MARKET_SNAPSHOT_PATH,
    RESEARCH_SIGNAL_PATH,
    TRADE_DECISION_PATH,
)

from bridge.research_trading_bridge import run_research_trading_bridge
from core.event_log import log_event
from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.order_executor import run_order_executor
from crypto_ai_system.execution.paper_book_kernel import (
    multibook_enabled,
    open_books,
    open_in_book,
    settle_books,
)
from crypto_ai_system.execution.paper_position_kernel import (
    has_open_position,
    load_open_position,
    open_from_execution,
    settle_open_position,
)
from crypto_ai_system.feedback.counterfactual_tracker import (
    record_blocked_signal,
    settle_counterfactuals,
)
from crypto_ai_system.execution.reconciler import run_reconciler
from crypto_ai_system.execution.signed_testnet_reconciliation import (
    run_signed_testnet_reconciliation,
)
from crypto_ai_system.trading.trading_cycle import run_trading_cycle

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult, ValidationVerdict


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


# Stage routing lives in trading_steps.stage_router (M1); these names stay
# importable/patchable here until the M5 call-site migration.
from crypto_ai_system.pipeline.trading_steps.stage_router import (  # noqa: E402
    _confirmation_present,
    _flag,
    _live_requested,
    _live_strategy_block_reason,
    _live_strategy_requested,
    _testnet_requested,
    resolve_execution_stage,
)
from crypto_ai_system.pipeline.trading_steps.context import CycleInputs  # noqa: E402


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

    @staticmethod
    def _verdict(ctx: PipelineContext) -> ValidationVerdict:
        """This cycle's validation verdict; an unwired context fails closed."""
        return ctx.verdict or ValidationVerdict.fail_closed()

    def _maybe_strategy_decision(self, ctx: PipelineContext, execution_stage: str, open_positions: int):
        """Build a strategy-driven trade decision from this cycle's router result.

        Isolated so a failure here can never break the research path: any error
        returns None and the research decision stands."""
        routing = ctx.strategy_routing
        if not isinstance(routing, dict):
            return None
        try:
            from crypto_ai_system.strategy_factory.strategy_execution_bridge import (
                build_strategy_decision_for_cycle,
            )

            verdict = self._verdict(ctx)
            cycle_id = ctx.cycle.cycle_id if ctx.cycle else None
            now = ctx.cycle.started_at_utc if ctx.cycle else None
            return build_strategy_decision_for_cycle(
                routing, execution_stage=execution_stage, open_positions=open_positions,
                data_health=verdict.data_health, risk=verdict.risk_status,
                cycle_id=cycle_id, now=now,
            )
        except Exception:  # noqa: BLE001 - never let the drive path break research
            return None

    def _strategy_decision_for_candidate(self, ctx: PipelineContext, execution_stage: str,
                                         open_positions: int, candidate: dict):
        """A strategy decision for ONE ranked candidate (multibook entry walk).

        The decision builder reads the routing's primary_* fields, so the
        candidate is presented as the primary of a shallow routing copy.
        Isolated like _maybe_strategy_decision: any failure returns None."""
        routing = ctx.strategy_routing
        if not isinstance(routing, dict):
            return None
        try:
            from crypto_ai_system.strategy_factory.strategy_execution_bridge import (
                build_strategy_decision_for_cycle,
            )

            candidate_routing = {
                **routing,
                "primary_strategy_id": candidate.get("strategy_id"),
                "primary_strategy_rule_hash": candidate.get("strategy_rule_hash"),
                "direction": candidate.get("direction"),
                "symbol": candidate.get("symbol"),
            }
            verdict = self._verdict(ctx)
            cycle_id = ctx.cycle.cycle_id if ctx.cycle else None
            now = ctx.cycle.started_at_utc if ctx.cycle else None
            return build_strategy_decision_for_cycle(
                candidate_routing, execution_stage=execution_stage, open_positions=open_positions,
                data_health=verdict.data_health, risk=verdict.risk_status,
                cycle_id=cycle_id, now=now,
            )
        except Exception:  # noqa: BLE001 - never let the drive path break research
            return None

    def _run_multibook_entries(self, ctx: PipelineContext, cfg, cycle_id, execution_stage: str,
                               research_decision: dict, open_count: int):
        """Multibook entry phase: ranked candidates first, then the research
        decision into the default book, bounded by the per-cycle entry budget.

        Every attempt runs the full unchanged chain — persist decision, order
        executor, paper reconciler, book kernel — so each entry is gated and
        audited exactly like a single-book entry, and the kernel remains the
        arbiter of the book/global/direction caps. Returns
        ``(entries, first_strategy_decision)``."""
        from crypto_ai_system.execution.paper_book_kernel import DEFAULT_BOOK_ID

        entries: list[dict] = []
        opened_count = 0
        budget = max(0, int(getattr(settings, "MULTIBOOK_MAX_ENTRIES_PER_CYCLE", 2)))
        taken_books = set(open_books(cfg))

        def _attempt(decision: dict, kind: str, book_hint: str) -> None:
            nonlocal opened_count
            atomic_write_json(TRADE_DECISION_PATH, decision)
            order = run_order_executor(execution_stage)
            order = order if isinstance(order, dict) else {}
            reconciliation = run_reconciler()
            opened, refusal = None, None
            if order.get("filled"):
                # enabled is passed explicitly: the caller decided the mode for
                # this cycle, and a mid-cycle settings flip must not split it.
                opened, refusal = open_in_book(
                    order, reconciliation if isinstance(reconciliation, dict) else {},
                    cycle_id=cycle_id, cfg=cfg, enabled=True,
                )
                if refusal:
                    log_event(
                        "multibook_open_refused",
                        {"reason": refusal, "book": book_hint, "cycle_id": cycle_id},
                        severity="WARNING",
                    )
                elif opened is not None:
                    opened_count += 1
                    taken_books.add(str(opened.get("book_id")))
            entries.append({
                "decision_kind": kind,
                "book": book_hint,
                "order": order,
                "reconciliation": reconciliation,
                "opened": opened,
                "book_refusal": refusal,
                "filled": bool(order.get("filled")),
                # The post-executor on-disk decision (carries the consumption
                # marker) so the walk can re-persist the EXECUTED entry's
                # decision at the end instead of last-writer-wins.
                "decision": read_json(TRADE_DECISION_PATH, {}),
            })

        strategy_drive = None
        routing = ctx.strategy_routing
        drive_on = _flag("STRATEGY_FACTORY_ROUTING_ENABLED") and _flag("STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED")
        candidates = []
        if drive_on and isinstance(routing, dict):
            candidates = [
                c for c in (routing.get("ranked_candidates") or [])
                if c.get("strategy_id") and c["strategy_id"] not in taken_books
            ]

        for candidate in candidates:
            if len(entries) >= budget:
                break
            decision = self._strategy_decision_for_candidate(
                ctx, execution_stage, open_count + opened_count, candidate,
            )
            # No executor churn on a candidate the bridge already refused.
            if decision is None or not decision.get("allow_order_intent"):
                continue
            if strategy_drive is None:
                strategy_drive = decision
            _attempt(decision, "strategy", str(candidate["strategy_id"]))

        # The research decision drives the shared default book, last: the pool's
        # strategies are the point of multibook, research keeps its one slot.
        if len(entries) < budget and DEFAULT_BOOK_ID not in taken_books and isinstance(research_decision, dict):
            _attempt(research_decision, "research", DEFAULT_BOOK_ID)

        return entries, strategy_drive

    def _settle_counterfactuals(self, inputs: CycleInputs) -> list[dict]:
        """Advance the shadow book of trades the gates blocked.

        Best-effort: counterfactual bookkeeping is observational, so a failure
        here must never disturb real execution."""
        if not _flag("COUNTERFACTUAL_TRACKING_ENABLED", True):
            return []
        try:
            return settle_counterfactuals(
                inputs.latest_candle,
                last_close=inputs.last_close,
                timeframe=inputs.timeframe,
                regime=inputs.regime,
                cfg=inputs.cfg,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort, but never silent
            log_event(
                "counterfactual_settle_failed",
                {"error": repr(exc)},
                severity="WARNING",
            )
            return []

    def _record_counterfactual(self, cfg, trade_decision: dict, snapshot: dict, cycle_id):
        """Shadow a signal the system wanted but did not take."""
        if not _flag("COUNTERFACTUAL_TRACKING_ENABLED", True):
            return None
        try:
            return record_blocked_signal(
                trade_decision,
                market_snapshot=snapshot,
                research_signal=read_json(RESEARCH_SIGNAL_PATH, {}),
                cycle_id=cycle_id,
                cfg=cfg,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort, but never silent
            log_event(
                "counterfactual_record_failed",
                {"error": repr(exc)},
                severity="WARNING",
            )
            return None

    def _settle_live_before_refusal(self) -> dict | None:
        """Settle the open live position even when the live stage is refused.

        A kill switch / cleared config blocks NEW entries, but must never
        abandon an already-open live position: SL/TP/time exits keep being
        evaluated and the reduceOnly close goes through the narrow close guard
        (which exempts closes from the kill switch — risk reduction). Any
        failure leaves the position OPEN (fail-open-position) and logs loudly.
        """
        if not _live_strategy_requested():
            return None
        try:
            from crypto_ai_system.execution.live_position_kernel import (
                has_open_live_position,
                settle_open_live_position,
            )

            cfg = load_config(".")
            if not has_open_live_position(cfg):
                return None
            snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
            return settle_open_live_position(
                _latest_candle(),
                last_close=_f(snapshot.get("last_close")),
                timeframe=str(snapshot.get("timeframe", "1h")),
                regime=str(snapshot.get("trend_bias", "unknown")),
                cfg=cfg,
            )
        except Exception as exc:  # noqa: BLE001 - never turn a refusal into a crash
            log_event(
                "live_settle_on_refused_stage_failed",
                {"error": repr(exc)},
                severity="ERROR",
            )
            return None

    def execute(self, ctx: PipelineContext) -> StageResult:
        # Fail-closed stage routing. The executor's final guard is the last
        # gate before anything is signed.
        execution_stage, block_reason = resolve_execution_stage()
        if block_reason:
            # Settle-first: the refusal must not strand an open live position.
            settlement = self._settle_live_before_refusal()
            if settlement is not None:
                return self.blocked(
                    [block_reason], fatal=True, live_settlement_on_refusal=settlement
                )
            return self.blocked([block_reason], fatal=True)

        verdict = self._verdict(ctx)
        allow_new_position = verdict.allow_new_position

        cfg = load_config(".")
        cycle_id = ctx.cycle.cycle_id if ctx.cycle else None
        snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
        # One market view per cycle: every step below shares THIS snapshot and
        # candle, so two reads of a mid-cycle-rewritten file cannot disagree.
        inputs = CycleInputs(
            cfg=cfg,
            stage=execution_stage,
            cycle_id=cycle_id,
            now=ctx.cycle.started_at_utc if ctx.cycle else None,
            snapshot=snapshot,
            latest_candle=_latest_candle(),
            verdict=verdict,
            routing=ctx.strategy_routing,
        )
        is_paper = execution_stage == "paper"
        is_live = execution_stage == "live"

        # 1. Settle any open position FIRST — SL/TP/time exit may close it and
        #    produce a CLOSED outcome before this cycle considers a new entry.
        #    Paper settles by simulation; live submits a REAL reduceOnly close
        #    (fail-open-position: a blocked/unconfirmed close stays OPEN).
        settlement = None
        book_settlements: list[dict] = []
        multibook = is_paper and multibook_enabled()
        if multibook:
            # Every open book settles independently on the same candle; each
            # closed summary carries its own position for S8/S9 attribution.
            book_settlements = settle_books(
                inputs.latest_candle,
                last_close=inputs.last_close,
                timeframe=inputs.timeframe,
                regime=inputs.regime,
                cfg=cfg,
                enabled=True,
            )
            settlement = book_settlements[0] if book_settlements else None
            if _flag("STRATEGY_FACTORY_ROUTING_ENABLED"):
                for closed in book_settlements:
                    position = closed.get("position")
                    if isinstance(position, dict) and position.get("strategy_id"):
                        self._record_strategy_outcome(position, closed, ctx)
        elif is_paper:
            # Capture the position before settling — settle clears it, and a
            # strategy-driven close must be attributed to its strategy (S8/S9).
            open_before = load_open_position(cfg)
            settlement = settle_open_position(
                inputs.latest_candle,
                last_close=inputs.last_close,
                timeframe=inputs.timeframe,
                regime=inputs.regime,
                cfg=cfg,
            )
            if (
                settlement is not None
                and isinstance(open_before, dict)
                and open_before.get("strategy_id")
                and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
            ):
                self._record_strategy_outcome(open_before, settlement, ctx)
        elif is_live:
            from crypto_ai_system.execution.live_pnl_ledger import live_risk_snapshot
            from crypto_ai_system.execution.live_position_kernel import (
                load_open_live_position,
                settle_open_live_position,
            )

            # Persist today's realized live P&L + breaker state each cycle so the
            # operator (and dashboard) can watch it and the daily-loss circuit
            # breaker's input is fresh.
            live_risk_snapshot()
            open_before = load_open_live_position(cfg)
            settlement = settle_open_live_position(
                inputs.latest_candle,
                last_close=inputs.last_close,
                timeframe=inputs.timeframe,
                regime=inputs.regime,
                cfg=cfg,
            )
            if (
                isinstance(settlement, dict)
                and settlement.get("status") == "CLOSED"
                and isinstance(open_before, dict)
                and open_before.get("strategy_id")
                and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
            ):
                self._record_strategy_outcome(open_before, settlement, ctx)

        # 1b. Settle the shadow book on the same candle. These are the trades the
        #     gates blocked; settling them with the kernel's exit math is what
        #     makes "the gate cost us 3R" a measurement rather than a guess.
        counterfactuals_settled = self._settle_counterfactuals(inputs)

        # 2. Open-position count for the gate (max_open_positions enforced there;
        #    multibook counts open books against the book cap).
        if is_live:
            from crypto_ai_system.execution.live_position_kernel import has_open_live_position

            open_positions = 1 if has_open_live_position(cfg) else 0
        elif multibook:
            open_positions = len(open_books(cfg))
        else:
            open_positions = 1 if (is_paper and has_open_position(cfg)) else 0

        trading = run_trading_cycle(allow_new_position=allow_new_position)
        trade_decision = run_research_trading_bridge(
            execution_stage=execution_stage, open_positions=open_positions,
            data_health=verdict.data_health, risk=verdict.risk_status,
        )

        # Strategy-factory drive (paper or live, opt-in): when a routed candidate
        # exists this cycle, replace the research decision with a strategy-driven
        # one. It is still gated by research permission + PreOrderRiskGate inside
        # the builder, and only overrides when it produces an order-intent-eligible
        # decision — otherwise the research decision stands (fail-closed). On the
        # live stage the L2 final guard additionally requires the persisted
        # stage='live' RiskGate record before anything is signed.
        strategy_drive = None
        multibook_entries: list[dict] = []
        if multibook:
            # M3: walk the ranked candidates (one book each), then the research
            # decision into the default book, bounded by the per-cycle entry
            # budget. The kernel's caps stay the arbiter inside the loop.
            multibook_entries, strategy_drive = self._run_multibook_entries(
                ctx, cfg, cycle_id, execution_stage, trade_decision, open_positions,
            )
            # The representative outcome of the walk is the entry that actually
            # FILLED (first fill wins), not whatever was attempted last — the
            # persisted decision, order, and reconciliation must all describe
            # the same executed trade. Falls back to the last attempt when
            # nothing filled.
            representative = next(
                (e for e in multibook_entries if e.get("filled")),
                multibook_entries[-1] if multibook_entries else {},
            )
            order = representative.get("order") or {}
            reconciliation = representative.get("reconciliation") or {}
            executed_decision = representative.get("decision")
            if isinstance(executed_decision, dict) and executed_decision:
                atomic_write_json(TRADE_DECISION_PATH, executed_decision)
                trade_decision = executed_decision
            externally_submitted = False
        else:
            drive_eligible = (
                (is_paper or execution_stage == "live")
                and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
                and _flag("STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED")
            )
            if drive_eligible:
                strategy_drive = self._maybe_strategy_decision(ctx, execution_stage, open_positions)
                if strategy_drive is not None and strategy_drive.get("allow_order_intent"):
                    atomic_write_json(TRADE_DECISION_PATH, strategy_drive)
                    trade_decision = strategy_drive

            order = run_order_executor(execution_stage)

            # Reconcile against the venue only when a real external order was
            # submitted; otherwise use the paper reconciler.
            externally_submitted = isinstance(order, dict) and order.get(
                "external_order_submission_performed"
            )
            if execution_stage == "signed_testnet" and externally_submitted:
                reconciliation = run_signed_testnet_reconciliation()
            elif execution_stage == "live" and externally_submitted:
                from crypto_ai_system.execution.live_strategy_execution import (
                    run_live_strategy_reconciliation,
                )

                reconciliation = run_live_strategy_reconciliation()
            else:
                reconciliation = run_reconciler()

        # Derive real order lifecycle state — a non-empty result dict is NOT a
        # trade (a REJECTED/NO_ORDER result is also a dict). A trade counts only
        # when the executor actually filled (paper) or submitted (testnet).
        # Multibook aggregates across this cycle's entry attempts.
        order = order if isinstance(order, dict) else {}
        order_status = order.get("status")
        if multibook:
            orders = [e.get("order") or {} for e in multibook_entries]
            order_filled = any(bool(o.get("filled")) for o in orders)
            order_intent_created = any(
                bool(o.get("intent", {}).get("order_intent_created")) or bool(o.get("order_intent_id"))
                for o in orders
            )
            order_submitted = False  # multibook is paper-only; nothing external
            trade_executed = order_filled
        else:
            order_filled = bool(order.get("filled"))
            order_intent_created = bool(order.get("intent", {}).get("order_intent_created")) or bool(
                order.get("order_intent_id")
            )
            order_submitted = bool(order.get("external_order_submission_performed")) or (
                order_status in {"SIGNED_TESTNET_ORDER_SUBMITTED", "LIVE_STRATEGY_ORDER_SUBMITTED"}
            )
            trade_executed = order_filled or order_status in {
                "SIGNED_TESTNET_ORDER_SUBMITTED", "LIVE_STRATEGY_ORDER_SUBMITTED",
            }

        # 2b. The signal wanted a trade and did not get one — shadow it, whatever
        #     stopped it. Recording keys off what actually happened (no trade),
        #     not off any single gate's verdict, so blocks upstream of the bridge
        #     are captured too.
        counterfactual_opened = None
        if not trade_executed:
            counterfactual_opened = self._record_counterfactual(
                cfg, trade_decision, snapshot, cycle_id
            )

        # 3. Open a canonical position from a freshly filled entry (only if none
        #    is open — the gate's max_open_positions already enforces this).
        #    Paper opens from the simulated fill; live opens from the REAL fill
        #    via its kernel (which requires a RECONCILED entry).
        opened = None
        book_open_refusal = None
        if multibook:
            # Opens already happened inside the entry walk (the kernel stayed
            # the arbiter there); surface the first for the legacy output shape.
            opened = next((e.get("opened") for e in multibook_entries if e.get("opened")), None)
            book_open_refusal = next(
                (e.get("book_refusal") for e in multibook_entries if e.get("book_refusal")), None
            )
        elif is_paper and order_filled and not has_open_position(cfg):
            opened = open_from_execution(
                order,
                reconciliation if isinstance(reconciliation, dict) else {},
                cycle_id=cycle_id,
                cfg=cfg,
            )
        elif is_live and externally_submitted:
            from crypto_ai_system.execution.live_position_kernel import (
                has_open_live_position,
                open_from_live_execution,
            )

            if not has_open_live_position(cfg):
                opened = open_from_live_execution(
                    order,
                    reconciliation if isinstance(reconciliation, dict) else {},
                    cycle_id=cycle_id,
                    cfg=cfg,
                )

        # Position lifecycle flows through the kernels, not Path A. A live close
        # counts only when it actually CLOSED (a failed close stays open).
        position_opened = opened is not None
        if is_live:
            position_closed = isinstance(settlement, dict) and settlement.get("status") == "CLOSED"
        elif multibook:
            position_closed = bool(book_settlements)
        else:
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
            # What the gates turned away this cycle, and which shadow trades the
            # candle resolved.
            "counterfactual_opened": counterfactual_opened,
            "counterfactuals_settled": counterfactuals_settled,
            # Multibook state (empty/None in single-book mode).
            "multibook_active": multibook,
            "book_settlements": book_settlements,
            "book_open_refusal": book_open_refusal,
            "open_books_count": open_positions if multibook else None,
            # This cycle's entry walk: which decisions ran, what filled, which
            # books opened or refused (order/reconciliation dicts included).
            "multibook_entries": multibook_entries,
        }

        if not allow_new_position:
            return self.degraded(
                ["ran in no-new-position mode (validation gate closed)"],
                **outputs,
            )
        return self.ok(**outputs)
