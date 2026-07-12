from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step248_canonical_order_executor_direct_place_order_is_blocked():
    from crypto_ai_system.execution.order_executor import (
        ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE,
        EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        ORDER_EXECUTOR_MODE,
        place_order,
    )

    assert ORDER_EXECUTOR_MODE == "GUARDED_REVIEW_ONLY"
    assert LIVE_TRADING_ALLOWED_BY_THIS_MODULE is False
    assert ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE is False
    assert EXTERNAL_ORDER_SUBMISSION_PERFORMED is False
    result = place_order({"symbol": "BTCUSDT", "side": "BUY"})
    assert result["status"] == "BLOCKED_STEP80"
    assert result["state"] == "REJECTED"
    assert result["external_order_submission_performed"] is False


def test_step248_canonical_order_executor_bridge_compat_is_review_only(tmp_path):
    from crypto_ai_system.execution.order_executor import execute_order_with_risk_check

    result = execute_order_with_risk_check(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=100000,
        current_price=100000,
        storage_dir=tmp_path,
        metadata={"source": "unit_test"},
    )
    assert result["status"] == "GUARDED_REVIEW_ONLY_BLOCKED"
    assert result["executed"] is False
    assert result["filled"] is False
    assert result["exchange_order_id"] is None
    assert result["live_trading_allowed_by_this_module"] is False
    assert result["adapter_routing_enabled_by_this_module"] is False
    assert result["external_order_submission_performed"] is False
    assert result["order_request"]["metadata"]["source"] == "unit_test"


def test_step248_batch5_report_confirms_order_executor_removed_from_plan(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step248_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step248_canonical_port_batch5.py",
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
    assert payload["status"] == "BATCH5_CANONICAL_PORT_APPLIED_GUARDED_REVIEW_ONLY"
    assert payload["direct_root_import_finding_count"] <= 11
    assert payload["remaining_root_only_input_count"] <= 11
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["order_executor_mode"] == "GUARDED_REVIEW_ONLY"
    assert payload["live_trading_allowed"] is False
    assert payload["adapter_routing_enabled"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
