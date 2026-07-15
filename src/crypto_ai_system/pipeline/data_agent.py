"""Data collection agent: market data -> snapshot -> context.

Wraps the existing collectors/builders. Emits DEGRADED (not OK) when the
underlying collector fell back to synthetic candles, so downstream stages
and the operator can see that a cycle ran on non-real data.
"""

from __future__ import annotations

from collectors.market_data_collector import collect_market_data
from builders.market_context import build_market_context
from builders.market_snapshot import build_market_snapshot

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult

_SYNTHETIC_MARKERS = ("synthetic", "fallback", "mock", "sample")


def _looks_synthetic(payload: object) -> bool:
    text = repr(payload).lower()
    return any(marker in text for marker in _SYNTHETIC_MARKERS)


class DataAgent(Agent):
    name = "data"
    fatal_on_error = True

    def execute(self, ctx: PipelineContext) -> StageResult:
        market_data = collect_market_data()
        snapshot = build_market_snapshot()
        context = build_market_context()

        if not context:
            return self.blocked(["market context not produced"], fatal=True)

        outputs = {
            "market_data": market_data,
            "market_snapshot": snapshot,
            "market_context": context,
        }

        if _looks_synthetic(market_data):
            return self.degraded(
                ["market data used synthetic/fallback source — not live-eligible"],
                data_is_synthetic=True,
                **outputs,
            )
        return self.ok(data_is_synthetic=False, **outputs)
