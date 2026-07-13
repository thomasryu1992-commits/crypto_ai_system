from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step250_canonical_research_engine_is_report_only(tmp_path, monkeypatch):
    import crypto_ai_system.research.research_engine as research_engine

    assert research_engine.RESEARCH_ENGINE_MODE == "RESEARCH_REPORT_ONLY"
    assert research_engine.TRADING_EXECUTION_ENABLED_BY_THIS_MODULE is False
    assert research_engine.ORDER_ROUTING_ENABLED_BY_THIS_MODULE is False

    market_context = {
        "snapshot": {
            "trend_bias": "bullish",
            "change_24h_pct": 2.0,
            "volume_ratio": 1.5,
            "funding_rate": 0.0,
            "open_interest_change_24h": 1.0,
        },
        "summary": {"symbol": "BTCUSDT"},
        "positives": ["trend_bullish"],
        "risks": [],
    }
    context_path = tmp_path / "market_context.json"
    result_path = tmp_path / "research_result.json"
    context_path.write_text(json.dumps(market_context), encoding="utf-8")
    monkeypatch.setattr(research_engine, "MARKET_CONTEXT_PATH", context_path)
    monkeypatch.setattr(research_engine, "RESEARCH_RESULT_PATH", result_path)

    result = research_engine.run_research_cycle()
    assert result["research_engine_mode"] == "RESEARCH_REPORT_ONLY"
    assert result["trading_execution_enabled_by_this_module"] is False
    assert result["order_routing_enabled_by_this_module"] is False
    assert result_path.exists()


def test_step250_canonical_research_decision_is_generation_only(tmp_path, monkeypatch):
    import crypto_ai_system.research.decision_engine as decision_engine

    assert decision_engine.RESEARCH_DECISION_MODE == "DECISION_GENERATION_ONLY"
    assert decision_engine.TRADING_EXECUTION_ENABLED_BY_THIS_MODULE is False
    assert decision_engine.ORDER_ROUTING_ENABLED_BY_THIS_MODULE is False

    research_result = {
        "scenario": "Constructive",
        "signal_quality": "B",
        "signal_timing": "Early",
        "scores": {"final_score": 62, "positives": ["constructive"], "risks": []},
    }
    input_path = tmp_path / "research_result.json"
    output_path = tmp_path / "research_decision.json"
    input_path.write_text(json.dumps(research_result), encoding="utf-8")
    monkeypatch.setattr(decision_engine, "RESEARCH_RESULT_PATH", input_path)
    monkeypatch.setattr(decision_engine, "RESEARCH_DECISION_PATH", output_path)

    decision = decision_engine.run_research_decision()
    assert decision["research_decision_mode"] == "DECISION_GENERATION_ONLY"
    assert decision["trading_execution_enabled_by_this_module"] is False
    assert decision["order_routing_enabled_by_this_module"] is False
    assert decision["allow_long"] is False
    assert decision["allow_new_position"] is False
    assert decision["risk_level"] == "blocked"
    assert decision["legacy_signal_fallback_blocker_blocks_decision"] is True
    assert output_path.exists()


def test_step250_batch7_report_confirms_research_modules_removed_from_plan(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step250_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step250_research_engine_port.py",
            "--output",
            str(output),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "BATCH7_CANONICAL_PORT_APPLIED_RESEARCH_ONLY"
    assert payload["direct_root_import_finding_count"] <= 3
    assert payload["remaining_root_only_input_count"] <= 3
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["research_engine_mode"] == "RESEARCH_REPORT_ONLY"
    assert payload["research_decision_mode"] == "DECISION_GENERATION_ONLY"
    assert payload["trading_execution_enabled"] is False
    assert payload["order_routing_enabled"] is False
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
