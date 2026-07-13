from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step254_missing_canonical_disposition_plan_outputs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "disposition_plan.json"
    csv_output = tmp_path / "disposition_plan.csv"
    md_output = tmp_path / "disposition_plan.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_missing_canonical_module_disposition.py",
            "--json-output",
            str(json_output),
            "--csv-output",
            str(csv_output),
            "--md-output",
            str(md_output),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json_output.exists()
    assert csv_output.exists()
    assert md_output.exists()

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["plan_type"] == "missing_canonical_module_disposition_plan"
    assert payload["status"] == "PLAN_ONLY_NO_PORT_OR_DELETE"
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["root_direct_imports_retired"] is True
    assert payload["missing_canonical_module_count"] <= 10
    assert payload["port_to_canonical_count"] <= 8
    assert payload["keep_explicit_legacy_compatibility_count"] == 2
    assert payload["retire_or_deprecate_count"] == 0
    assert payload["port_performed"] is False
    assert payload["wrapper_conversion_performed"] is False
    assert payload["root_package_deletion_performed"] is False
    assert payload["live_trading_allowed"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["rows"]


def test_step254_execution_sensitive_modules_are_not_auto_enabled(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "disposition_plan.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/plan_missing_canonical_module_disposition.py",
            "--json-output",
            str(json_output),
            "--csv-output",
            str(tmp_path / "disposition_plan.csv"),
            "--md-output",
            str(tmp_path / "disposition_plan.md"),
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    rows = {row["legacy_module"]: row for row in payload["rows"]}

    assert rows["execution.live_executor"]["disposition"] == "KEEP_EXPLICIT_LEGACY_COMPATIBILITY"
    assert rows["execution.testnet_executor"]["disposition"] == "KEEP_EXPLICIT_LEGACY_COMPATIBILITY"
    if "execution.exchange_router" in rows:
        assert rows["execution.exchange_router"]["disposition"] == "PORT_TO_CANONICAL"
        assert rows["execution.exchange_router"]["risk_level"] == "HIGH"
        assert "add_disabled_or_review_only_safety_flags" in rows["execution.exchange_router"]["required_repairs"]
    for module in ["execution.live_executor", "execution.testnet_executor"]:
        assert rows[module]["uses_network_or_exchange_boundary"] is True


def test_step254_next_batch_is_execution_support():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from plan_missing_canonical_module_disposition import build_missing_canonical_disposition_plan

    payload = build_missing_canonical_disposition_plan(root)
    assert payload["next_step"]["name"] == "Step255 v5 Execution Support Canonical Port Batch"
    step255_modules = {
        row["legacy_module"]
        for row in payload["rows"]
        if row["target_step"] == "Step255"
    }
    assert step255_modules.issubset({"execution.order_models", "execution.order_state", "execution.mock_exchange", "execution.exchange_router"})
    assert payload["missing_canonical_module_count"] <= 10
