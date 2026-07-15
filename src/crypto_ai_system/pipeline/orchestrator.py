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

from crypto_ai_system.pipeline.contracts import (
    PipelineContext,
    PipelineRun,
    StageResult,
    StageStatus,
)
from crypto_ai_system.pipeline.data_agent import DataAgent
from crypto_ai_system.pipeline.feedback_agent import FeedbackAgent
from crypto_ai_system.pipeline.research_agent import ResearchAgent
from crypto_ai_system.pipeline.trading_agent import TradingAgent
from crypto_ai_system.pipeline.validation_agent import ValidationAgent


class Pipeline:
    def __init__(self) -> None:
        self.pre_trade = [DataAgent(), ResearchAgent(), ValidationAgent()]
        self.trading = TradingAgent()
        self.feedback = FeedbackAgent()

    def run_once(self) -> PipelineRun:
        ctx = PipelineContext()
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
        )


def run_pipeline_once() -> PipelineRun:
    return Pipeline().run_once()
