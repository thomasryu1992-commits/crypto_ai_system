from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step249_canonical_reconciler_is_check_only():
    from crypto_ai_system.execution.reconciler import (
        EXTERNAL_EXECUTION_SYNC_PERFORMED,
        LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE,
        RECONCILER_MODE,
        reconcile_execution_state,
    )

    assert RECONCILER_MODE == "CHECK_ONLY"
    assert LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE is False
    assert EXTERNAL_EXECUTION_SYNC_PERFORMED is False
    result = reconcile_execution_state()
    assert result["status"] == "NO_LIVE_EXECUTION"
    assert result["reconciler_mode"] == "CHECK_ONLY"
    assert result["live_position_sync_enabled_by_this_module"] is False
    assert result["external_execution_sync_performed"] is False


def test_step249_canonical_execution_reconciliation_is_check_only(tmp_path):
    from crypto_ai_system.execution.execution_reconciler import (
        EXECUTION_RECONCILIATION_MODE,
        EXTERNAL_EXECUTION_SYNC_PERFORMED,
        LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE,
        run_execution_reconciliation,
    )

    assert EXECUTION_RECONCILIATION_MODE == "CHECK_ONLY"
    assert LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE is False
    assert EXTERNAL_EXECUTION_SYNC_PERFORMED is False
    result = run_execution_reconciliation(tmp_path)
    assert result["safety"]["execution_reconciliation_mode"] == "CHECK_ONLY"
    assert result["safety"]["live_position_sync_enabled_by_this_module"] is False
    assert result["safety"]["external_execution_sync_performed"] is False


def test_step249_batch6_report_confirms_reconcilers_removed_from_plan(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step249_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step249_execution_reconciler_port.py",
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
    assert payload["status"] == "BATCH6_CANONICAL_PORT_APPLIED_CHECK_ONLY"
    assert payload["direct_root_import_finding_count"] <= 8
    assert payload["remaining_root_only_input_count"] <= 8
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["reconciler_mode"] == "CHECK_ONLY"
    assert payload["live_position_sync_enabled"] is False
    assert payload["external_execution_sync_performed"] is False
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
