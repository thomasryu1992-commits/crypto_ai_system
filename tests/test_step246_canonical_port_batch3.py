from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step246_canonical_live_guard_is_readiness_only_and_default_blocked():
    from crypto_ai_system.execution.live_guard import (
        EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        LIVE_GUARD_MODE,
        LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        run_live_readiness_check,
    )

    readiness = run_live_readiness_check()
    assert LIVE_GUARD_MODE == "READINESS_CHECK_ONLY"
    assert LIVE_TRADING_ALLOWED_BY_THIS_MODULE is False
    assert EXTERNAL_ORDER_SUBMISSION_PERFORMED is False
    assert readiness["live_guard_mode"] == "READINESS_CHECK_ONLY"
    assert readiness["live_trading_allowed_by_this_module"] is False
    assert readiness["external_order_submission_performed"] is False
    assert readiness["ready"] is False
    assert readiness["secret_metadata_boundary"]["secret_value_accessed"] is False
    assert readiness["secret_metadata_boundary"]["api_secret_value_access_allowed"] is False
    assert len(readiness["blockers"]) > 0


def test_step246_batch3_report_confirms_live_guard_removed_from_plan(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step246_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step246_canonical_port_batch3.py",
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
    assert payload["status"] == "BATCH3_CANONICAL_PORT_APPLIED_READINESS_ONLY"
    assert payload["direct_root_import_finding_count"] <= 18
    assert payload["remaining_root_only_input_count"] <= 18
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["live_guard_mode"] == "READINESS_CHECK_ONLY"
    assert payload["live_trading_allowed"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
