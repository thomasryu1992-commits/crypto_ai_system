from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


def test_step256_paper_watch_is_report_only(tmp_path, monkeypatch):
    import crypto_ai_system.trading.paper_watch as paper_watch

    assert paper_watch.PAPER_WATCH_MODE == "PAPER_REPORT_ONLY"
    assert paper_watch.ORDER_EXECUTION_ENABLED_BY_THIS_MODULE is False
    assert paper_watch.LIVE_TRADING_ALLOWED_BY_THIS_MODULE is False
    assert paper_watch.EXTERNAL_ORDER_SUBMISSION_PERFORMED is False

    monkeypatch.setattr(paper_watch, "STORAGE_DIR", tmp_path)
    result = paper_watch.finalize_paper_watch({"signal": "NONE"}, 100000)
    assert result["status"] == "PAPER_WATCH_FINALIZED"
    assert result["position_opened"] is False
    assert result["external_order_submission_performed"] is False
    assert (tmp_path / "paper_watch_result.json").exists()
    assert (tmp_path / "reports" / "paper_performance_report.json").exists()


def test_step256_legacy_research_v1_flow_is_research_only(tmp_path, monkeypatch):
    import crypto_ai_system.research.dynamic_setup_generator as dynamic_setup
    import crypto_ai_system.research.research_cycle as research_cycle
    import crypto_ai_system.research.research_decision as research_decision

    monkeypatch.setattr(dynamic_setup, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(research_cycle, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(research_decision, "STORAGE_DIR", tmp_path)

    (tmp_path / "market_context.json").write_text(
        json.dumps({"market_bias": "bullish", "funding_state": "neutral", "oi_state": "increasing", "current_price": 100000}),
        encoding="utf-8",
    )

    setup = dynamic_setup.generate_dynamic_setup()
    cycle = research_cycle.run_research_cycle()
    decision = research_decision.make_research_decision()

    assert setup["dynamic_setup_mode"] == "RESEARCH_ONLY_LEGACY_V1"
    assert setup["trading_execution_enabled_by_this_module"] is False
    assert setup["order_routing_enabled_by_this_module"] is False

    assert cycle["research_cycle_mode"] == "RESEARCH_REPORT_ONLY_LEGACY_V1"
    assert cycle["trading_execution_enabled_by_this_module"] is False
    assert cycle["order_routing_enabled_by_this_module"] is False

    assert decision["research_decision_legacy_v1_mode"] == "RESEARCH_DECISION_ONLY_LEGACY_V1"
    assert decision["trading_execution_enabled_by_this_module"] is False
    assert decision["order_routing_enabled_by_this_module"] is False
    assert (tmp_path / "research_decision_result.json").exists()


def test_step256_legacy_imports_reexport_canonical_modules():
    legacy_paper_watch = importlib.import_module("trading.paper_watch")
    legacy_dynamic_setup = importlib.import_module("research.dynamic_setup_generator")
    legacy_research_cycle = importlib.import_module("research.research_cycle")
    legacy_research_decision = importlib.import_module("research.research_decision")

    assert legacy_paper_watch.PAPER_WATCH_MODE == "PAPER_REPORT_ONLY"
    assert legacy_dynamic_setup.DYNAMIC_SETUP_MODE == "RESEARCH_ONLY_LEGACY_V1"
    assert legacy_research_cycle.RESEARCH_CYCLE_MODE == "RESEARCH_REPORT_ONLY_LEGACY_V1"
    assert legacy_research_decision.RESEARCH_DECISION_LEGACY_V1_MODE == "RESEARCH_DECISION_ONLY_LEGACY_V1"


def test_step256_report_confirms_missing_count_reduced_to_deferred_only(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step256_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step256_paper_research_v1_port.py",
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
    assert payload["status"] == "PAPER_RESEARCH_LEGACY_V1_CANONICAL_PORT_APPLIED"
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["missing_canonical_module_count_after"] == 2
    assert len(payload["step256_wrapper_modules"]) == 4
    assert payload["port_performed"] is True
    assert payload["wrapper_conversion_performed"] is True
    assert payload["root_package_deletion_performed"] is False
    assert payload["trading_execution_enabled"] is False
    assert payload["order_routing_enabled"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["deferred_modules"] == ["execution.live_executor", "execution.testnet_executor"]
