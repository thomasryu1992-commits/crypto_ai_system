"""Base class for pipeline agents.

An agent wraps one stage of the trading loop. Subclasses implement
:meth:`execute`; the base class handles timing and fail-closed error
capture so a crash in one stage becomes an ``ERROR`` StageResult rather
than tearing down the whole cycle.
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod

from crypto_ai_system.pipeline.contracts import (
    PipelineContext,
    StageResult,
    StageStatus,
)


class Agent(ABC):
    #: Stable stage name used as the StageResult key.
    name: str = "agent"

    #: When True, a BLOCKED/ERROR result from this agent halts the trade path.
    fatal_on_error: bool = True

    def run(self, ctx: PipelineContext) -> StageResult:
        start = time.perf_counter()
        try:
            result = self.execute(ctx)
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary
            result = StageResult(
                stage=self.name,
                status=StageStatus.ERROR,
                reasons=[f"{type(exc).__name__}: {exc}"],
                outputs={f"{self.name}_traceback": traceback.format_exc()},
                fatal=self.fatal_on_error,
            )
        result.duration_ms = (time.perf_counter() - start) * 1000.0
        # Stamp cycle lineage on every stage output.
        if ctx.cycle is not None:
            result.outputs.setdefault("cycle_id", ctx.cycle.cycle_id)
        return result

    @abstractmethod
    def execute(self, ctx: PipelineContext) -> StageResult:
        """Run the stage and return its result. May raise; run() catches."""
        raise NotImplementedError

    # -- helpers ---------------------------------------------------------
    def ok(self, **outputs) -> StageResult:
        return StageResult(stage=self.name, status=StageStatus.OK, outputs=outputs)

    def degraded(self, reasons: list[str], **outputs) -> StageResult:
        return StageResult(
            stage=self.name,
            status=StageStatus.DEGRADED,
            reasons=reasons,
            outputs=outputs,
        )

    def blocked(self, reasons: list[str], fatal: bool = True, **outputs) -> StageResult:
        return StageResult(
            stage=self.name,
            status=StageStatus.BLOCKED,
            reasons=reasons,
            outputs=outputs,
            fatal=fatal,
        )
