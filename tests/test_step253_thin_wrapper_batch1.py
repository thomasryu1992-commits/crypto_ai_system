from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


def test_step253_legacy_imports_still_work_through_thin_wrappers():
    execution_idempotency = importlib.import_module("execution.idempotency")
    execution_retry_policy = importlib.import_module("execution.retry_policy")
    trading_atr = importlib.import_module("trading.atr")
    trading_permission_gate = importlib.import_module("trading.permission_gate")
    trading_cycle = importlib.import_module("trading.trading_cycle")
    research_scoring = importlib.import_module("research.scoring")
    research_scenario = importlib.import_module("research.scenario")

    assert callable(execution_idempotency.make_idempotency_key)
    assert execution_retry_policy.classify_exchange_error(status_code=429)["reason"] == "rate_limit"
    assert trading_atr.true_range({"high": 10, "low": 8, "close": 9}, None) == 2
    assert trading_permission_gate.signal_payload_from_research_signal({"entry_side": "NONE"})["signal"] == "NONE"
    assert trading_cycle.TRADING_CYCLE_MODE == "PAPER_SHADOW_DECISION_ONLY"
    assert callable(trading_cycle.run_trading_cycle)
    assert research_scoring.score_market_context({"snapshot": {}})["final_score"] >= 0
    assert research_scenario.classify_scenario(50) == "Neutral"


def test_step253_missing_canonical_modules_remain_unconverted_files():
    root = Path(__file__).resolve().parents[1]
    missing_modules = [
        "execution/live_executor.py",
        "execution/testnet_executor.py",
    ]
    for rel in missing_modules:
        text = (root / rel).read_text(encoding="utf-8")
        assert "Step253 thin wrapper" not in text
        assert "from crypto_ai_system." not in text or "import *" not in text


def test_step253_batch1_report_confirms_partial_wrapper_conversion(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step253_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step253_thin_wrapper_batch1.py",
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
    assert payload["status"] == "BATCH1_THIN_WRAPPER_CONVERSION_APPLIED"
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["root_direct_imports_retired"] is True
    assert payload["thin_wrapper_converted_count"] == 18
    assert payload["canonical_module_missing_count"] <= 10
    assert payload["full_wrapper_conversion_ready"] is False
    assert payload["full_wrapper_conversion_blocked"] is True
    assert payload["wrapper_conversion_performed"] is True
    assert payload["root_package_deletion_performed"] is False
    assert payload["missing_canonical_modules_untouched"] is True
    assert payload["live_trading_allowed"] is False
    assert payload["paper_execution_enabled"] is False
    assert payload["adapter_routing_enabled"] is False
