"""A small, restart-safe scheduling loop for the trading pipeline.

Runs a callable every ``interval`` seconds for ``cycles`` iterations (or
forever). A failing cycle is caught and recorded — one bad cycle never stops
the loop. Every collaborator (sleep, clock) is injectable so the loop is
unit-testable without real time passing.
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable

RunCycle = Callable[[], Any]
SleepFn = Callable[[float], None]
Clock = Callable[[], float]
OnResult = Callable[[dict], None]


def run_scheduler_loop(
    run_cycle: RunCycle,
    *,
    cycles: int | None = None,
    interval: float = 3600.0,
    sleep_fn: SleepFn = time.sleep,
    clock: Clock = time.monotonic,
    on_result: OnResult | None = None,
) -> list[dict]:
    """Run ``run_cycle`` repeatedly. Returns a record per cycle.

    ``cycles=None`` runs until interrupted. A cycle that raises is recorded
    with ``ok=False`` and the loop continues (fail-open on transient errors,
    since the pipeline itself fails closed on trading).
    """
    records: list[dict] = []
    completed = 0
    while cycles is None or completed < cycles:
        completed += 1
        started = clock()
        try:
            result = run_cycle()
            record = {"cycle": completed, "ok": True, "result": result, "error": None}
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            record = {
                "cycle": completed,
                "ok": False,
                "result": None,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        record["duration_s"] = round(clock() - started, 3)
        records.append(record)

        if on_result is not None:
            on_result(record)

        if cycles is not None and completed >= cycles:
            break
        sleep_fn(interval)

    return records
