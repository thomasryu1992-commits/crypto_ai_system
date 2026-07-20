"""CycleInputs: everything a trading step needs, gathered once per cycle.

One snapshot read and one candle read per cycle instead of scattered
``read_json`` calls — the steps receive the same view of the market, so two
reads of a mid-cycle-rewritten file can no longer disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crypto_ai_system.artifacts import MarketSnapshotView
from crypto_ai_system.config import AppConfig
from crypto_ai_system.pipeline.contracts import ValidationVerdict


@dataclass(frozen=True)
class CycleInputs:
    """Immutable per-cycle inputs shared by every trading step.

    The market-derived accessors delegate to the typed
    :class:`~crypto_ai_system.artifacts.MarketSnapshotView` so field names,
    fallback chains, and defaults live in ONE place instead of being re-derived
    here. ``snapshot`` stays the raw mapping for output/audit compatibility.
    """

    cfg: AppConfig
    stage: str
    cycle_id: str | None
    now: str | None
    snapshot: Mapping[str, Any]
    latest_candle: Mapping[str, Any] | None
    verdict: ValidationVerdict
    routing: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "_market", MarketSnapshotView.from_mapping(self.snapshot))

    @property
    def market(self) -> MarketSnapshotView:
        return self._market  # type: ignore[attr-defined]

    @property
    def is_paper(self) -> bool:
        return self.stage == "paper"

    @property
    def is_live(self) -> bool:
        return self.stage == "live"

    @property
    def last_close(self) -> float | None:
        return self.market.last_close

    @property
    def timeframe(self) -> str:
        return self.market.timeframe

    @property
    def regime(self) -> str:
        return self.market.trend_bias
