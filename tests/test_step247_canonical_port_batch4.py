from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step247_canonical_paper_engine_is_paper_only_and_sl_first():
    from crypto_ai_system.trading.paper_engine import (
        EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        PAPER_ENGINE_MODE,
        build_paper_position,
        update_position_conservative,
    )

    assert PAPER_ENGINE_MODE == "PAPER_ONLY"
    assert LIVE_TRADING_ALLOWED_BY_THIS_MODULE is False
    assert EXTERNAL_ORDER_SUBMISSION_PERFORMED is False

    position = build_paper_position("LONG", 100.0, "step247_unit")
    candle = {
        "high": position["take_profit"] + 1,
        "low": position["stop_loss"] - 1,
        "close": 100,
    }
    closed, active = update_position_conservative(position, candle)
    assert closed["result"] == "LOSS"
    assert active is None
    assert closed["intrabar_policy"] == "pessimistic_sl_first"


def test_step247_canonical_position_sizing_available():
    from crypto_ai_system.trading.position_sizing import calculate_position_size

    sizing = calculate_position_size(100.0, 95.0)
    assert sizing["quantity"] >= 0
    assert sizing["notional_usdt"] >= 0
    assert sizing["reason"] in {"position_size_by_risk_with_notional_cap", "invalid_entry_or_stop"}


def test_step247_batch4_report_confirms_paper_engine_removed_from_plan(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step247_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step247_canonical_port_batch4.py",
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
    assert payload["status"] == "BATCH4_CANONICAL_PORT_APPLIED_PAPER_ONLY"
    assert payload["direct_root_import_finding_count"] <= 15
    assert payload["remaining_root_only_input_count"] <= 15
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["paper_engine_mode"] == "PAPER_ONLY"
    assert payload["live_trading_allowed"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
