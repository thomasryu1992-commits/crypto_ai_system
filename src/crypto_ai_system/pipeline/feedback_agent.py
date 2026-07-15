"""Feedback agent: outcome analytics -> performance report -> candidate.

Closes the loop. Per the core principle, feedback produces *candidates*,
never live runtime changes: it records outcomes and writes a candidate
profile for later manual approval. It runs every cycle regardless of whether
a trade was placed, so the system keeps learning from no-trade cycles too.
"""

from __future__ import annotations

from crypto_ai_system.feedback.candidate_profile_registry import (
    run_candidate_profile_latest,
)
from crypto_ai_system.feedback.outcome_analytics_v2 import run_outcome_analytics_latest
from crypto_ai_system.feedback.performance_report_generator import (
    run_performance_report_latest,
)

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult


class FeedbackAgent(Agent):
    name = "feedback"
    # Feedback failures should never halt anything — the loop is already done.
    fatal_on_error = False

    def execute(self, ctx: PipelineContext) -> StageResult:
        outcome = run_outcome_analytics_latest()
        performance = run_performance_report_latest()
        candidate = run_candidate_profile_latest()

        return self.ok(
            outcome=outcome,
            performance_report=performance,
            candidate_profile=candidate,
        )
