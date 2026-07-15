"""Exit-code policy for a pipeline run.

A fatal BLOCK (safety halt) or an ERROR must never look like a clean success to
Windows Task Scheduler or external monitoring. This maps a :class:`PipelineRun`
to a documented exit code plus a human halt reason.

    0  normal (trade placed)
    2  normal, no trade this cycle
    10 halted by a safety policy (fatal BLOCK)
    20 data / research / validation error
    30 trading / execution error
    50 feedback / storage / registry error
"""

from __future__ import annotations

from crypto_ai_system.pipeline.contracts import PipelineRun, StageStatus

EXIT_OK = 0
EXIT_NO_TRADE = 2
EXIT_SAFETY_BLOCK = 10
EXIT_UPSTREAM_ERROR = 20
EXIT_TRADING_ERROR = 30
EXIT_FEEDBACK_ERROR = 50

# Codes that mean "the cycle did NOT complete healthily".
UNHEALTHY_CODES = frozenset({EXIT_SAFETY_BLOCK, EXIT_UPSTREAM_ERROR, EXIT_TRADING_ERROR, EXIT_FEEDBACK_ERROR})


def exit_code_for(run: PipelineRun) -> tuple[int, str | None]:
    """Return ``(exit_code, halt_reason)`` for a completed run."""
    for result in run.results:
        if result.status is StageStatus.ERROR:
            if result.stage == "trading":
                return EXIT_TRADING_ERROR, result.summary()
            if result.stage == "feedback":
                return EXIT_FEEDBACK_ERROR, result.summary()
            return EXIT_UPSTREAM_ERROR, result.summary()
        if result.status is StageStatus.BLOCKED and result.fatal:
            return EXIT_SAFETY_BLOCK, result.summary()

    if not run.trade_executed:
        return EXIT_NO_TRADE, None
    return EXIT_OK, None


def is_healthy(code: int) -> bool:
    """A no-trade cycle (2) is healthy; only halts/errors are not."""
    return code not in UNHEALTHY_CODES
