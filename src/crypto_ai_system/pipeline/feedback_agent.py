"""Feedback agent: outcome analytics -> performance report -> candidate.

Closes the loop. Per the core principle, feedback produces *candidates*,
never live runtime changes: it records outcomes and writes a candidate
profile for later manual approval. It runs every cycle regardless of whether
a trade was placed, so the system keeps learning from no-trade cycles too.
"""

from __future__ import annotations

import config.settings as settings

from core.event_log import log_event
from crypto_ai_system.feedback.candidate_profile_registry import (
    run_candidate_profile_latest,
)
from crypto_ai_system.feedback.gate_calibration_report import (
    run_gate_calibration_report_latest,
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

    def _strategy_lifecycle(self, ctx: PipelineContext):
        """Recompute S9/S10 for the active pool from attributed paper outcomes.

        Best-effort and only when the strategy factory is active; a failure here
        never affects the rest of feedback."""
        if not getattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", False):
            return None
        try:
            from crypto_ai_system.feedback.strategy_feedback_step import (
                run_strategy_lifecycle_feedback,
            )

            now = ctx.cycle.started_at_utc if ctx.cycle else None
            return run_strategy_lifecycle_feedback(
                pool_file=str(settings.ACTIVE_STRATEGY_POOL_PATH),
                outcome_registry_file=str(settings.STRATEGY_ATTRIBUTED_OUTCOME_REGISTRY_PATH),
                lifecycle_registry_file=str(settings.STRATEGY_LIFECYCLE_REGISTRY_PATH),
                now=now,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort, but never silent
            log_event(
                "strategy_lifecycle_feedback_failed",
                {"error": repr(exc)},
                severity="WARNING",
            )
            return None

    def _gate_calibration(self):
        """Score each block reason by what its blocked trades would have done.

        Best-effort and review-only: it never retunes a gate, and a failure here
        must not cost us the rest of the feedback cycle."""
        if not getattr(settings, "COUNTERFACTUAL_TRACKING_ENABLED", True):
            return None
        try:
            return run_gate_calibration_report_latest()
        except Exception as exc:  # noqa: BLE001 - best-effort, but never silent
            log_event(
                "gate_calibration_report_failed",
                {"error": repr(exc)},
                severity="WARNING",
            )
            return None

    def execute(self, ctx: PipelineContext) -> StageResult:
        outcome = run_outcome_analytics_latest()
        performance = run_performance_report_latest()
        candidate = run_candidate_profile_latest()
        strategy_lifecycle = self._strategy_lifecycle(ctx)
        gate_calibration = self._gate_calibration()

        return self.ok(
            outcome=outcome,
            performance_report=performance,
            candidate_profile=candidate,
            strategy_lifecycle=strategy_lifecycle,
            gate_calibration=gate_calibration,
        )
