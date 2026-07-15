"""Lean five-agent trading pipeline.

data -> research -> validation -> trading -> feedback

Each stage is an independent :class:`~crypto_ai_system.pipeline.base.Agent`
that wraps the existing core modules. The :class:`Pipeline` orchestrator
chains them with fail-closed gating.
"""

from crypto_ai_system.pipeline.contracts import (
    PipelineContext,
    PipelineRun,
    StageResult,
    StageStatus,
)
from crypto_ai_system.pipeline.orchestrator import Pipeline, run_pipeline_once

__all__ = [
    "Pipeline",
    "run_pipeline_once",
    "PipelineContext",
    "PipelineRun",
    "StageResult",
    "StageStatus",
]
