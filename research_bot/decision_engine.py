from __future__ import annotations

from knowledge_engine.research_decision_builder import build_research_decision


def run_decision_engine() -> dict:
    return build_research_decision()
