"""Single source for the scenario/timing -> directional permission mapping.

This mapping was previously duplicated (with drifting membership) across
``research_engine``, ``active_research_signal`` and ``decision_engine``.
Every module that needs to know whether the research view permits a long or
a short must derive it from here.

The scenario sets are public because they are the only record of the
research's *directional view* before timing/data blocks collapse the entry
side to FLAT — the counterfactual tracker reads them to know what a block
suppressed.
"""

from __future__ import annotations

LONG_SCENARIOS = {"Bullish", "Constructive"}
SHORT_SCENARIOS = {"Bearish"}
BLOCKING_TIMING = {"Data-Blocked", "Late", "Risk-Off", "Bearish"}


def directional_permission(scenario: str, timing: str) -> tuple[bool, bool]:
    """Return ``(allow_long, allow_short)`` from scenario/timing alone.

    Data-quality blocks (synthetic/fallback) are layered on top by the
    ResearchSignal builder; this function is only the directional view.
    """
    allow_long = scenario in LONG_SCENARIOS and timing not in BLOCKING_TIMING
    allow_short = scenario in SHORT_SCENARIOS and timing != "Data-Blocked"
    return allow_long, allow_short
