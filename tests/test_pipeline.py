"""Tests for the lean five-agent pipeline.

Unit tests exercise the orchestrator's fail-closed gating with fake agents;
an integration smoke test runs the real pipeline once.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import (
    PipelineContext,
    StageResult,
    StageStatus,
)
from crypto_ai_system.pipeline.orchestrator import Pipeline


class _FakeAgent(Agent):
    def __init__(self, name: str, result: StageResult) -> None:
        self.name = name
        self._result = result
        self.ran = False

    def execute(self, ctx: PipelineContext) -> StageResult:
        self.ran = True
        return self._result


def _pipeline_with(pre_trade, trading, feedback) -> Pipeline:
    pipe = Pipeline()
    pipe.pre_trade = pre_trade
    pipe.trading = trading
    pipe.feedback = feedback
    return pipe


def test_happy_path_runs_all_stages():
    pre = [
        _FakeAgent("data", StageResult("data", StageStatus.OK)),
        _FakeAgent("research", StageResult("research", StageStatus.OK)),
        _FakeAgent(
            "validation",
            StageResult("validation", StageStatus.OK, outputs={"allow_new_position": True}),
        ),
    ]
    trading = _FakeAgent(
        "trading",
        StageResult("trading", StageStatus.OK, outputs={"trade_executed": True}),
    )
    feedback = _FakeAgent("feedback", StageResult("feedback", StageStatus.OK))

    run = _pipeline_with(pre, trading, feedback).run_once()

    assert [r.stage for r in run.results] == [
        "data",
        "research",
        "validation",
        "trading",
        "feedback",
    ]
    assert trading.ran is True
    assert run.trade_executed is True
    assert not run.halted


def test_upstream_error_skips_trading_but_runs_feedback():
    pre = [
        _FakeAgent("data", StageResult("data", StageStatus.OK)),
        _FakeAgent(
            "research",
            StageResult("research", StageStatus.ERROR, reasons=["boom"], fatal=True),
        ),
        _FakeAgent("validation", StageResult("validation", StageStatus.OK)),
    ]
    trading = _FakeAgent("trading", StageResult("trading", StageStatus.OK))
    feedback = _FakeAgent("feedback", StageResult("feedback", StageStatus.OK))

    run = _pipeline_with(pre, trading, feedback).run_once()

    # validation never runs (research halted), trading is SKIPPED, feedback runs.
    assert pre[2].ran is False
    assert trading.ran is False
    assert feedback.ran is True
    trading_result = run.by_stage("trading")
    assert trading_result is not None
    assert trading_result.status is StageStatus.SKIPPED
    assert run.halted


def test_degraded_validation_does_not_halt():
    pre = [
        _FakeAgent("data", StageResult("data", StageStatus.OK)),
        _FakeAgent("research", StageResult("research", StageStatus.OK)),
        _FakeAgent(
            "validation",
            StageResult(
                "validation",
                StageStatus.DEGRADED,
                reasons=["no-trade gate"],
                outputs={"allow_new_position": False},
            ),
        ),
    ]
    trading = _FakeAgent("trading", StageResult("trading", StageStatus.DEGRADED))
    feedback = _FakeAgent("feedback", StageResult("feedback", StageStatus.OK))

    run = _pipeline_with(pre, trading, feedback).run_once()

    assert trading.ran is True  # degraded is not a halt
    assert not run.halted


def test_agent_exception_becomes_error_result():
    class _Boom(Agent):
        name = "data"

        def execute(self, ctx: PipelineContext) -> StageResult:
            raise RuntimeError("kaboom")

    result = _Boom().run(PipelineContext())
    assert result.status is StageStatus.ERROR
    assert result.halts is True
    assert any("kaboom" in r for r in result.reasons)


@pytest.mark.integration
def test_real_pipeline_runs_once():
    """Smoke: the real pipeline completes a cycle without an ERROR stage."""
    run = Pipeline().run_once()
    stages = [r.stage for r in run.results]
    assert stages == ["data", "research", "validation", "trading", "feedback"]
    assert not any(r.status is StageStatus.ERROR for r in run.results), run.report()
