from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step244_canonical_retry_policy_matches_legacy_behavior():
    from crypto_ai_system.execution.retry_policy import classify_exchange_error

    assert classify_exchange_error(status_code=429)["reason"] == "rate_limit"
    assert classify_exchange_error(error_name="Network Timeout")["state"] == "UNKNOWN"
    assert "QUERY" in classify_exchange_error(error_name="Network Timeout")["action"]
    assert classify_exchange_error(status_code=400)["state"] == "REJECTED"
    assert classify_exchange_error(status_code=500)["retry"] is True


def test_step244_canonical_atr_stop_distance_guard():
    from crypto_ai_system.trading.atr import calculate_atr, stop_distance_bps_from_atr, true_range

    candle = {"high": 105, "low": 95, "close": 100}
    assert true_range(candle, None) == 10

    candles = []
    price = 100.0
    for _ in range(20):
        candles.append({"open": price, "high": price + 0.01, "low": price - 0.01, "close": price, "volume": 100})
    assert calculate_atr(candles) is not None
    info = stop_distance_bps_from_atr(price, candles)
    assert info["final_stop_distance_bps"] >= info["min_stop_loss_bps"]
    assert info["final_stop_distance_bps"] <= info["max_stop_loss_bps"]


def test_step244_batch1_report_confirms_ported_modules_removed_from_plan(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step244_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step244_canonical_port_batch1.py",
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
    assert payload["status"] == "BATCH1_CANONICAL_PORT_APPLIED"
    assert payload["direct_root_import_finding_count"] <= 23
    assert payload["remaining_root_only_input_count"] <= 23
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
    assert payload["live_trading_allowed"] is False
