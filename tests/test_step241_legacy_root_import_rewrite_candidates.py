from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step241_low_risk_candidates_are_rewritten(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step241_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step241_import_rewrite_candidates.py",
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
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["low_risk_rewrite_candidate_remaining_count"] == 0
    assert payload["manual_mapping_imports_untouched"] == 0
    assert payload["wrapper_conversion_performed"] is False
    assert payload["live_trading_allowed"] is False
    assert payload["paper_execution_enabled"] is False
    assert payload["adapter_routing_enabled"] is False


def test_step241_canonical_modules_export_legacy_names():
    from crypto_ai_system.execution.idempotency import make_client_order_id, make_idempotency_key
    from crypto_ai_system.trading.permission_gate import signal_payload_from_research_signal
    from crypto_ai_system.trading.permission_audit import log_permission_gate_audit

    key = make_idempotency_key("BTCUSDT", "LONG", "s1", "t1", "sig1")
    assert make_client_order_id("BTCUSDT", "LONG", key).startswith("CAI_BTCUSDT_LONG_")
    payload = signal_payload_from_research_signal({
        "entry_side": "LONG",
        "entry_allowed": True,
        "trade_permission": {
            "allow_long": True,
            "allow_short": False,
            "allow_new_position": True,
            "risk_level": "normal",
        },
    })
    assert payload["signal"] == "LONG"
    assert callable(log_permission_gate_audit)
