"""Data collection agent: market data -> snapshot -> context.

Wraps the existing collectors/builders. Emits DEGRADED (not OK) when the
underlying collector fell back to synthetic candles, so downstream stages
and the operator can see that a cycle ran on non-real data.
"""

from __future__ import annotations

from collectors.market_data_collector import collect_market_data
from builders.market_context import build_market_context
from builders.market_snapshot import build_market_snapshot

from core.event_log import log_event
from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult

_REAL_QUALITY = "real"


def _looks_synthetic(payload: object) -> bool:
    """Authoritative check on the collector's own flags (not a text scan)."""
    if not isinstance(payload, dict):
        return True
    if payload.get("is_synthetic") or payload.get("is_fallback"):
        return True
    quality = str(payload.get("data_quality", "")).lower()
    return quality != _REAL_QUALITY


class DataAgent(Agent):
    name = "data"
    fatal_on_error = True

    def _venue_basis_probe(self):
        """Read-only Extended basis sampling (venue design V4). Best-effort:
        the probe measures the cross-venue price basis for the future basis
        guard and must never cost the cycle its market data."""
        import config.settings as settings

        if not getattr(settings, "EXTENDED_BASIS_PROBE_ENABLED", False):
            return None
        try:
            from crypto_ai_system.data.extended_basis_probe import run_extended_basis_probe

            return run_extended_basis_probe()
        except Exception as exc:  # noqa: BLE001 - best-effort, but never silent
            log_event(
                "extended_basis_probe_failed",
                {"error": repr(exc)},
                severity="WARNING",
            )
            return None

    def execute(self, ctx: PipelineContext) -> StageResult:
        market_data = collect_market_data()
        snapshot = build_market_snapshot()
        context = build_market_context()

        if not context:
            return self.blocked(["market context not produced"], fatal=True)

        venue_basis = self._venue_basis_probe()

        outputs = {
            "market_data": market_data,
            "market_snapshot": snapshot,
            "market_context": context,
            "venue_basis": venue_basis,
        }

        if _looks_synthetic(market_data):
            return self.degraded(
                ["market data used synthetic/fallback source - not live-eligible"],
                data_is_synthetic=True,
                **outputs,
            )
        return self.ok(data_is_synthetic=False, **outputs)
