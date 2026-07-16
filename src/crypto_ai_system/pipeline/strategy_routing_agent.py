"""Strategy routing agent — the first live-pipeline touchpoint (shadow mode).

Runs the multi-strategy entry router (S7) against the *live* feature row each
cycle and records what the active strategy pool would do. It is deliberately
advisory: it writes a routing artifact and stage output, but does not create an
order, size a position, or change any execution flag. Turning a routed candidate
into an actual paper entry is a later, separately-reviewed increment.

Fail-open toward *not trading* and fail-closed toward *safety*: the agent never
halts the pipeline (``fatal_on_error = False``), and it is gated behind
``STRATEGY_FACTORY_ROUTING_ENABLED`` (default false), so the live path is
byte-identical when the flag is off. An empty pool, missing candles, or an
evaluation error all resolve to "no entry", never to an order.
"""

from __future__ import annotations

from typing import Any

import config.settings as settings
from core.json_io import atomic_write_json, read_json

from crypto_ai_system.strategy_factory.active_strategy_pool import occupying_entries
from crypto_ai_system.strategy_factory.entry_strategy_router_agent import route_entries
from crypto_ai_system.strategy_factory.runtime_feature_adapter import (
    build_runtime_feature_row_for_timeframe,
)

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult

STATUS_DISABLED = "DISABLED"
STATUS_NO_ACTIVE_STRATEGIES = "NO_ACTIVE_STRATEGIES"
STATUS_NO_FEATURE_ROW = "NO_FEATURE_ROW"


def runtime_base_timeframe() -> str:
    """The pipeline's own candle timeframe, as a spec timeframe string."""
    from collectors.real_market_data import to_binance_interval

    return to_binance_interval(str(getattr(settings, "TIMEFRAME", "PT1H")))


def _pool_timeframes(pool: dict) -> set[str]:
    return {
        str((e.get("strategy_spec") or {}).get("timeframe") or "")
        for e in occupying_entries(pool)
    } - {""}


def evaluate_live_routing(pool: dict, candles: list[dict], *, now: str | None = None) -> dict[str, Any]:
    """Build a feature row per pool timeframe and route the active pool.

    Each spec is evaluated on the timeframe it was backtested on: base-timeframe
    specs use the pipeline's own candles, others load their series from the
    deep-history cache. A timeframe whose row cannot be built leaves its specs
    unevaluable (fail-closed to no-entry) without blocking the rest of the pool.
    """
    if not occupying_entries(pool):
        return {"status": STATUS_NO_ACTIVE_STRATEGIES, "order_candidate_count": 0}

    base_tf = runtime_base_timeframe()
    feature_rows = {
        tf: build_runtime_feature_row_for_timeframe(
            tf, candles, base_timeframe=base_tf, now=now
        )
        for tf in _pool_timeframes(pool)
    }
    if not any(feature_rows.values()):
        return {"status": STATUS_NO_FEATURE_ROW, "order_candidate_count": 0}
    return route_entries(pool, {}, feature_rows=feature_rows, now=now)


class StrategyRoutingAgent(Agent):
    name = "strategy_routing"
    # Advisory only — a failure here must never halt the trade path.
    fatal_on_error = False

    def execute(self, ctx: PipelineContext) -> StageResult:
        if not getattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", False):
            return self.ok(strategy_routing_enabled=False,
                           strategy_routing={"status": STATUS_DISABLED, "order_candidate_count": 0})

        now = ctx.cycle.started_at_utc if ctx.cycle else None
        pool = read_json(settings.ACTIVE_STRATEGY_POOL_PATH, {}) or {}
        market_data = read_json(settings.MARKET_DATA_PATH, {}) or {}
        candles = market_data.get("candles", []) if isinstance(market_data, dict) else []

        result = evaluate_live_routing(pool, candles, now=now)
        # Shadow: persist for observability; drives nothing.
        result["shadow_mode"] = True
        result["drives_execution"] = False
        atomic_write_json(settings.STRATEGY_ROUTING_PATH, result)

        return self.ok(
            strategy_routing_enabled=True,
            strategy_routing=result,
            strategy_routing_shadow=True,
        )
