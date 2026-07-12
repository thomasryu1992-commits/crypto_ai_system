from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step251_canonical_trading_cycle_is_paper_shadow_only(tmp_path, monkeypatch):
    import crypto_ai_system.trading.trading_cycle as trading_cycle

    assert trading_cycle.TRADING_CYCLE_MODE == "PAPER_SHADOW_DECISION_ONLY"
    assert trading_cycle.ORDER_EXECUTION_ENABLED_BY_THIS_MODULE is False
    assert trading_cycle.LIVE_TRADING_ALLOWED_BY_THIS_MODULE is False
    assert trading_cycle.EXTERNAL_ORDER_SUBMISSION_PERFORMED is False

    snapshot_path = tmp_path / "market_snapshot.json"
    output_path = tmp_path / "trading_cycle.json"
    snapshot_path.write_text(json.dumps({"symbol": "BTCUSDT", "last_close": 100000}), encoding="utf-8")
    monkeypatch.setattr(trading_cycle, "MARKET_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(trading_cycle, "TRADING_CYCLE_PATH", output_path)

    monkeypatch.setattr(
        trading_cycle,
        "generate_trading_signal",
        lambda: {
            "signal": "NONE",
            "confidence": 0,
            "permission_gate_applied": True,
            "allow_long": False,
            "allow_short": False,
            "allow_new_position": False,
            "risk_level": "blocked",
            "position_size_multiplier": 0.0,
            "block_reasons": ["unit_test"],
            "risk_warnings": [],
        },
    )
    monkeypatch.setattr(
        trading_cycle,
        "run_paper_cycle",
        lambda signal, snapshot, allow_new_position=True: {
            "status": "NO_SIGNAL",
            "allow_new_position": allow_new_position,
            "signal": signal.get("signal"),
        },
    )
    monkeypatch.setattr(
        trading_cycle,
        "log_permission_gate_audit",
        lambda signal, paper, snapshot: {"status": "AUDIT_BUILT", "paper_status": paper.get("status")},
    )
    monkeypatch.setattr(
        trading_cycle,
        "build_and_save_paper_risk_level_report",
        lambda: {"status": "PAPER_RISK_LEVEL_REPORT_BUILT"},
    )

    result = trading_cycle.run_trading_cycle(allow_new_position=True)
    assert result["trading_cycle_mode"] == "PAPER_SHADOW_DECISION_ONLY"
    assert result["order_execution_enabled_by_this_module"] is False
    assert result["live_trading_allowed_by_this_module"] is False
    assert result["external_order_submission_performed"] is False
    assert result["paper_result"]["status"] == "NO_SIGNAL"
    assert output_path.exists()


def test_step251_canonical_signal_engine_is_generation_only():
    from crypto_ai_system.trading.signal_engine import (
        LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        ORDER_EXECUTION_ENABLED_BY_THIS_MODULE,
        SIGNAL_ENGINE_MODE,
    )

    assert SIGNAL_ENGINE_MODE == "SIGNAL_GENERATION_ONLY"
    assert ORDER_EXECUTION_ENABLED_BY_THIS_MODULE is False
    assert LIVE_TRADING_ALLOWED_BY_THIS_MODULE is False


def test_step251_batch8_report_confirms_all_root_imports_retired(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step251_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step251_trading_cycle_port.py",
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
    assert payload["status"] == "BATCH8_CANONICAL_PORT_APPLIED_PAPER_SHADOW_ONLY"
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["remaining_root_only_input_count"] == 0
    assert payload["remaining_port_group_count"] == 0
    assert payload["root_direct_imports_retired"] is True
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["trading_cycle_mode"] == "PAPER_SHADOW_DECISION_ONLY"
    assert payload["order_execution_enabled"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
