"""Inter-agent data contracts for the lean trading pipeline.

Each agent returns a :class:`StageResult`. The orchestrator threads a
:class:`PipelineContext` through the agents so later stages can read the
booleans and payloads produced by earlier ones, while the on-disk JSON
handoff under ``storage/latest/`` remains the source of truth for the
underlying core modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageStatus(str, Enum):
    """Outcome of a single agent run."""

    OK = "OK"
    """Stage completed and produced its expected output."""

    DEGRADED = "DEGRADED"
    """Stage completed but a soft precondition failed (e.g. no-trade gate)."""

    SKIPPED = "SKIPPED"
    """Stage did not run because an upstream stage halted the pipeline."""

    BLOCKED = "BLOCKED"
    """Stage refused to proceed; fatal blocks halt the pipeline (fail-closed)."""

    ERROR = "ERROR"
    """Stage raised an unexpected exception; halts the trade path only when
    fatal (advisory stages run with ``fatal_on_error = False``)."""


@dataclass
class StageResult:
    stage: str
    status: StageStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    fatal: bool = False
    """When True and status is BLOCKED/ERROR, the orchestrator halts the
    trade path (feedback still runs). When False, a non-OK status degrades
    but does not halt."""

    duration_ms: float | None = None

    @property
    def halts(self) -> bool:
        return self.fatal and self.status in {StageStatus.ERROR, StageStatus.BLOCKED}

    def summary(self) -> str:
        reason = f" — {'; '.join(self.reasons)}" if self.reasons else ""
        return f"[{self.status.value}] {self.stage}{reason}"


@dataclass
class CycleEnvelope:
    """Identity shared by every artifact produced in one pipeline cycle.

    The cycle_id ties DataSnapshot -> ResearchSignal -> Decision -> RiskGate ->
    OrderIntent -> Execution -> Reconciliation -> Outcome together so lineage
    can be verified and cross-cycle reuse detected.
    """

    cycle_id: str
    started_at_utc: str
    stage: str = "paper"


@dataclass
class PipelineContext:
    """Mutable state threaded through the agents within one cycle."""

    cycle: CycleEnvelope | None = None
    results: dict[str, StageResult] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def record(self, result: StageResult) -> None:
        self.results[result.stage] = result
        self.data.update(result.outputs)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def stage_ok(self, stage: str) -> bool:
        result = self.results.get(stage)
        return result is not None and result.status is StageStatus.OK


@dataclass
class PipelineRun:
    results: list[StageResult]
    trade_executed: bool = False
    cycle_id: str | None = None

    @property
    def halted(self) -> bool:
        return any(r.halts for r in self.results)

    def by_stage(self, stage: str) -> StageResult | None:
        for result in self.results:
            if result.stage == stage:
                return result
        return None

    def report(self) -> str:
        lines = [r.summary() for r in self.results]
        return "\n".join(lines)
