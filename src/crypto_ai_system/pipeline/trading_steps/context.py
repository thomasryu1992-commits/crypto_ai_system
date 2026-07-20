"""CycleInputs: everything a trading step needs, gathered once per cycle.

One snapshot read and one candle read per cycle instead of scattered
``read_json`` calls — the steps receive the same view of the market, so two
reads of a mid-cycle-rewritten file can no longer disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.pipeline.contracts import ValidationVerdict


def _f(value: Any) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CycleInputs:
    """Immutable per-cycle inputs shared by every trading step."""

    cfg: AppConfig
    stage: str
    cycle_id: str | None
    now: str | None
    snapshot: Mapping[str, Any]
    latest_candle: Mapping[str, Any] | None
    verdict: ValidationVerdict
    routing: Mapping[str, Any] | None

    @property
    def is_paper(self) -> bool:
        return self.stage == "paper"

    @property
    def is_live(self) -> bool:
        return self.stage == "live"

    @property
    def last_close(self) -> float | None:
        return _f(self.snapshot.get("last_close"))

    @property
    def timeframe(self) -> str:
        return str(self.snapshot.get("timeframe", "1h"))

    @property
    def regime(self) -> str:
        return str(self.snapshot.get("trend_bias", "unknown"))
