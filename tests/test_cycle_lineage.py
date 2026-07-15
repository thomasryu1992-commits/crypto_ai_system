"""Tests for cycle_id lineage (P0-3 foundation)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import (
    CycleEnvelope,
    PipelineContext,
    StageResult,
    StageStatus,
)


class _Echo(Agent):
    name = "echo"

    def execute(self, ctx: PipelineContext) -> StageResult:
        return self.ok(value=1)


def test_agent_stamps_cycle_id_from_context():
    ctx = PipelineContext(cycle=CycleEnvelope(cycle_id="cycle_abc", started_at_utc="t"))
    result = _Echo().run(ctx)
    assert result.outputs["cycle_id"] == "cycle_abc"


def test_no_cycle_means_no_stamp():
    ctx = PipelineContext()  # no envelope
    result = _Echo().run(ctx)
    assert "cycle_id" not in result.outputs


def test_pipeline_run_has_unique_cycle_id_per_run():
    from crypto_ai_system.pipeline import Pipeline

    run1 = Pipeline().run_once()
    run2 = Pipeline().run_once()
    assert run1.cycle_id and run1.cycle_id.startswith("cycle_")
    assert run2.cycle_id and run2.cycle_id != run1.cycle_id
    for r in run1.results:
        if r.status is not StageStatus.SKIPPED:
            assert r.outputs.get("cycle_id") == run1.cycle_id
