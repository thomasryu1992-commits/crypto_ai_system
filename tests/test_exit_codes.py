"""Tests for pipeline exit-code policy (P0-6)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.pipeline.contracts import PipelineRun, StageResult, StageStatus
from crypto_ai_system.pipeline.exit_codes import (
    EXIT_FEEDBACK_ERROR,
    EXIT_NO_TRADE,
    EXIT_OK,
    EXIT_SAFETY_BLOCK,
    EXIT_TRADING_ERROR,
    EXIT_UPSTREAM_ERROR,
    exit_code_for,
    is_healthy,
)


def _run(results, trade_executed=False):
    return PipelineRun(results=results, trade_executed=trade_executed)


def _ok(stage):
    return StageResult(stage=stage, status=StageStatus.OK)


ALL_OK = ["data", "research", "validation", "trading", "feedback"]


def test_normal_with_trade_is_zero():
    run = _run([_ok(s) for s in ALL_OK], trade_executed=True)
    assert exit_code_for(run) == (EXIT_OK, None)


def test_no_trade_is_two_and_healthy():
    run = _run([_ok(s) for s in ALL_OK], trade_executed=False)
    code, reason = exit_code_for(run)
    assert code == EXIT_NO_TRADE
    assert reason is None
    assert is_healthy(code) is True  # no-trade is a normal cycle


def test_fatal_block_is_ten_and_unhealthy():
    results = [
        _ok("data"),
        StageResult(stage="research", status=StageStatus.BLOCKED, fatal=True, reasons=["no signal"]),
    ]
    code, reason = exit_code_for(_run(results))
    assert code == EXIT_SAFETY_BLOCK
    assert "research" in reason
    assert is_healthy(code) is False


def test_non_fatal_block_does_not_halt():
    # validation DEGRADED-style block that is not fatal should not trip the code.
    results = [_ok("data"), _ok("research"), _ok("validation"), _ok("trading"), _ok("feedback")]
    assert exit_code_for(_run(results, trade_executed=True))[0] == EXIT_OK


def test_upstream_error_is_twenty():
    results = [_ok("data"), StageResult(stage="research", status=StageStatus.ERROR, reasons=["boom"])]
    assert exit_code_for(_run(results))[0] == EXIT_UPSTREAM_ERROR


def test_trading_error_is_thirty():
    results = [_ok("data"), _ok("research"), _ok("validation"),
               StageResult(stage="trading", status=StageStatus.ERROR, reasons=["exec fail"])]
    assert exit_code_for(_run(results))[0] == EXIT_TRADING_ERROR


def test_feedback_error_is_fifty():
    results = [_ok(s) for s in ("data", "research", "validation", "trading")]
    results.append(StageResult(stage="feedback", status=StageStatus.ERROR, reasons=["registry"]))
    code = exit_code_for(_run(results))[0]
    assert code == EXIT_FEEDBACK_ERROR
    assert is_healthy(code) is False
