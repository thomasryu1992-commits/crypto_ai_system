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
from typing import Any, Mapping


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
        # ASCII separator: this line goes to consoles that may be cp949.
        reason = f" - {'; '.join(self.reasons)}" if self.reasons else ""
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


@dataclass(frozen=True)
class ValidationVerdict:
    """The validation stage's complete verdict for ONE cycle.

    This is the REQUIRED input to every decision builder: an entry path that
    does not receive a verdict cannot be written (TypeError at call time),
    which is the structural fix for the audit's gate-bypass class. A missing
    verdict resolves to :meth:`fail_closed`, never to "allowed".
    """

    allow_new_position: bool
    data_health: Mapping[str, Any]
    risk_status: Mapping[str, Any]

    @classmethod
    def fail_closed(cls) -> "ValidationVerdict":
        """The verdict an unwired caller gets: everything blocked."""
        return cls(allow_new_position=False, data_health={}, risk_status={})

    @classmethod
    def from_latest_files(cls) -> "ValidationVerdict":
        """EXPLICIT file-based loader for standalone entry points.

        Module ``__main__``s and operator scripts run outside a pipeline cycle
        and must name their verdict source — this is that name. Missing or
        empty files fail closed through the same booleans the validation agent
        uses.
        """
        from config.settings import DATA_HEALTH_PATH, RISK_STATUS_PATH
        from core.json_io import read_json

        data_health = read_json(DATA_HEALTH_PATH, {}) or {}
        risk_status = read_json(RISK_STATUS_PATH, {}) or {}
        return cls(
            allow_new_position=bool(data_health.get("allow_trading"))
            and bool(risk_status.get("allow_new_position")),
            data_health=data_health,
            risk_status=risk_status,
        )


@dataclass
class PipelineContext:
    """Mutable state threaded through the agents within one cycle.

    The typed slots ARE the intra-cycle contract: ``verdict`` is set by the
    validation agent, ``strategy_routing`` by the routing agent, and consumers
    read those fields — there is no shared outputs namespace to remember keys
    in (the legacy merged dict was how the gate-bypass class slipped through).
    Everything else flows through each stage's own :class:`StageResult` or the
    ``storage/latest`` files.
    """

    cycle: CycleEnvelope | None = None
    results: dict[str, StageResult] = field(default_factory=dict)
    verdict: ValidationVerdict | None = None
    strategy_routing: dict[str, Any] | None = None

    def record(self, result: StageResult) -> None:
        self.results[result.stage] = result


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
