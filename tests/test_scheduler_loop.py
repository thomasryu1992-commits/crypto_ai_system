"""Tests for the scheduler loop (no real time passes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.scheduler.loop import run_scheduler_loop


def _fake_clock():
    """Deterministic monotonic clock: advances 1.0 per call."""
    t = {"v": 0.0}

    def clock():
        t["v"] += 1.0
        return t["v"]

    return clock


def test_runs_fixed_number_of_cycles():
    calls = []
    records = run_scheduler_loop(
        lambda: calls.append(1) or "ok",
        cycles=3,
        sleep_fn=lambda _s: None,
        clock=_fake_clock(),
    )
    assert len(calls) == 3
    assert len(records) == 3
    assert all(r["ok"] for r in records)
    assert [r["cycle"] for r in records] == [1, 2, 3]


def test_sleep_between_cycles_not_after_last():
    sleeps = []
    run_scheduler_loop(
        lambda: "ok",
        cycles=3,
        interval=42.0,
        sleep_fn=lambda s: sleeps.append(s),
        clock=_fake_clock(),
    )
    # Sleeps between cycles only: 2 for 3 cycles.
    assert sleeps == [42.0, 42.0]


def test_failing_cycle_is_recorded_and_loop_continues():
    state = {"n": 0}

    def run_cycle():
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("boom")
        return "ok"

    records = run_scheduler_loop(
        run_cycle, cycles=3, sleep_fn=lambda _s: None, clock=_fake_clock()
    )
    assert records[0]["ok"] is True
    assert records[1]["ok"] is False
    assert "boom" in records[1]["error"]
    assert records[2]["ok"] is True  # loop kept going


def test_on_result_called_each_cycle():
    seen = []
    run_scheduler_loop(
        lambda: "ok",
        cycles=2,
        sleep_fn=lambda _s: None,
        clock=_fake_clock(),
        on_result=lambda rec: seen.append(rec["cycle"]),
    )
    assert seen == [1, 2]
