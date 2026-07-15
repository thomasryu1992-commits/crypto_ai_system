"""Pipeline orchestrator: chains the five agents into one cycle.

Order: data -> research -> validation -> trading -> feedback.

Fail-closed semantics:
  * If any pre-trade stage (data/research/validation) halts (ERROR, or a
    fatal BLOCK), the trading stage is SKIPPED — no orders on bad inputs.
  * A DEGRADED pre-trade stage (e.g. validation's no-trade gate) does not
    halt; trading runs in no-new-position mode.
  * Feedback always runs so the system learns from every cycle.
"""

from __future__ import annotations

import uuid

import config.settings as settings
from core.time_utils import utc_now_iso

from crypto_ai_system.pipeline.contracts import (
    CycleEnvelope,
    PipelineContext,
    PipelineRun,
    StageResult,
    StageStatus,
)
from crypto_ai_system.pipeline.data_agent import DataAgent
from crypto_ai_system.pipeline.feedback_agent import FeedbackAgent
from crypto_ai_system.pipeline.research_agent import ResearchAgent
from crypto_ai_system.pipeline.strategy_routing_agent import StrategyRoutingAgent
from crypto_ai_system.pipeline.trading_agent import TradingAgent
from crypto_ai_system.pipeline.validation_agent import ValidationAgent


def _new_cycle() -> CycleEnvelope:
    stage = getattr(settings, "RUNTIME_STAGE", None) or "paper"
    return CycleEnvelope(
        cycle_id=f"cycle_{uuid.uuid4().hex[:16]}",
        started_at_utc=utc_now_iso(),
        stage=str(stage),
    )


class Pipeline:
    def __init__(self) -> None:
        self.pre_trade = [DataAgent(), ResearchAgent(), ValidationAgent()]
        # Strategy-factory routing runs after validation (so it can see the
        # gate) but only when explicitly enabled — the default pipeline is
        # unchanged. It is advisory (shadow) and never halts the trade path.
        if getattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", False):
            self.pre_trade.append(StrategyRoutingAgent())
        self.trading = TradingAgent()
        self.feedback = FeedbackAgent()

    def run_once(self) -> PipelineRun:
        ctx = PipelineContext(cycle=_new_cycle())
        results: list[StageResult] = []
        halted = False

        for agent in self.pre_trade:
            result = agent.run(ctx)
            ctx.record(result)
            results.append(result)
            if result.halts:
                halted = True
                break

        if halted:
            skipped = StageResult(
                stage=self.trading.name,
                status=StageStatus.SKIPPED,
                reasons=["upstream stage halted the pipeline (fail-closed)"],
            )
            ctx.record(skipped)
            results.append(skipped)
        else:
            trade_result = self.trading.run(ctx)
            ctx.record(trade_result)
            results.append(trade_result)

        feedback_result = self.feedback.run(ctx)
        ctx.record(feedback_result)
        results.append(feedback_result)

        return PipelineRun(
            results=results,
            trade_executed=bool(ctx.get("trade_executed", False)),
            cycle_id=ctx.cycle.cycle_id if ctx.cycle else None,
        )


def run_pipeline_once() -> PipelineRun:
    return Pipeline().run_once()
