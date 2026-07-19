"""The scenario/timing -> direction mapping must have one source of truth.

Previously three modules each hardcoded slightly different scenario/timing
sets; a decision could carry side=LONG while the signal's trade_permission
denied the long. These tests pin the shared mapping and the decision engine's
use of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.research.active_research_signal import _trade_permission
from crypto_ai_system.research.trade_permission import directional_permission


def test_directional_permission_long():
    assert directional_permission("Bullish", "Early") == (True, False)
    assert directional_permission("Constructive", "Neutral") == (True, False)
    # Blocking timings deny the long.
    for timing in ("Data-Blocked", "Late", "Risk-Off", "Bearish"):
        assert directional_permission("Bullish", timing) == (False, False)


def test_directional_permission_short():
    assert directional_permission("Bearish", "Early") == (False, True)
    assert directional_permission("Bearish", "Data-Blocked") == (False, False)
    # Cautious is risk-off, never a short permission.
    assert directional_permission("Cautious", "Early") == (False, False)


def test_signal_trade_permission_matches_shared_mapping():
    snapshot = {"is_synthetic": False, "is_fallback": False}
    for scenario in ("Bullish", "Constructive", "Bearish", "Cautious", "Neutral"):
        for timing in ("Early", "Late", "Risk-Off", "Data-Blocked", "Bearish"):
            perm = _trade_permission(snapshot, {"scenario": scenario, "signal_timing": timing})
            assert (perm["allow_long"], perm["allow_short"]) == directional_permission(scenario, timing)


def test_decision_side_agrees_with_directional_permission(monkeypatch, tmp_path):
    import crypto_ai_system.research.decision_engine as de

    monkeypatch.setattr(de, "RESEARCH_RESULT_PATH", tmp_path / "research_result.json")
    monkeypatch.setattr(de, "RESEARCH_SIGNAL_PATH", tmp_path / "research_signal.json")
    monkeypatch.setattr(de, "SIGNAL_QA_REPORT_PATH", tmp_path / "signal_qa_report.json")
    monkeypatch.setattr(de, "RESEARCH_DECISION_PATH", tmp_path / "research_decision.json")
    monkeypatch.setattr(de, "DECISION_PIPELINE_REGISTRY_RECORD_PATH", tmp_path / "registry_record.json")
    monkeypatch.setattr(de, "persist_decision_pipeline_registry_record", lambda *a, **k: {})

    from core.json_io import atomic_write_json

    cases = [
        ({"scenario": "Bullish", "signal_timing": "Early"}, "LONG"),
        # Risk-off timing denies the long everywhere now — side must not claim it.
        ({"scenario": "Bullish", "signal_timing": "Risk-Off"}, "NONE"),
        ({"scenario": "Bearish", "signal_timing": "Early"}, "SHORT"),
        # Data-blocked denies the short (fail-closed, same as the signal).
        ({"scenario": "Bearish", "signal_timing": "Data-Blocked"}, "NONE"),
        ({"scenario": "Cautious", "signal_timing": "Early"}, "NONE"),
    ]
    for research, expected_side in cases:
        atomic_write_json(tmp_path / "research_result.json", research)
        decision = de.run_research_decision()
        assert decision["side"] == expected_side, (research, decision["side"])
