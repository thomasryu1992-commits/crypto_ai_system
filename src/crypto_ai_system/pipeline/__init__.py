"""Lean five-agent trading pipeline.

data -> research -> validation -> trading -> feedback

Each stage is an independent :class:`~crypto_ai_system.pipeline.base.Agent`
that wraps the existing core modules. The :class:`Pipeline` orchestrator
chains them with fail-closed gating.
"""

from crypto_ai_system.pipeline.contracts import (
    CycleEnvelope,
    PipelineContext,
    PipelineRun,
    StageResult,
    StageStatus,
)
from crypto_ai_system.pipeline.orchestrator import Pipeline

__all__ = [
    "Pipeline",
    "CycleEnvelope",
    "PipelineContext",
    "PipelineRun",
    "StageResult",
    "StageStatus",
]
