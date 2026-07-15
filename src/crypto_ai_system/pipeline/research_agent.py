"""Research agent: research cycle -> research decision.

Wraps the research engine (transparent scoring) and the decision engine
(Allowed / Reduced / Blocked / Neutral / Review-only). Produces no trade
by itself — only a research signal and a research-level decision.
"""

from __future__ import annotations

from crypto_ai_system.research.active_research_signal import run_active_research_signal
from crypto_ai_system.research.decision_engine import run_research_decision
from crypto_ai_system.research.research_engine import run_research_cycle

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult


class ResearchAgent(Agent):
    name = "research"
    fatal_on_error = True

    def execute(self, ctx: PipelineContext) -> StageResult:
        research = run_research_cycle()
        # Emit a ResearchSignal v2 (lineage ids + hashes + trade_permission) from
        # the active data BEFORE the decision engine reads it, so the decision and
        # the real PreOrderRiskGate share one cycle's signal (E-2).
        cycle_id = ctx.cycle.cycle_id if ctx.cycle else None
        signal = run_active_research_signal(cycle_id=cycle_id)
        decision = run_research_decision()

        if not research or not decision:
            return self.blocked(
                ["research cycle or decision not produced"], fatal=True
            )

        return self.ok(research=research, research_signal=signal, research_decision=decision)
