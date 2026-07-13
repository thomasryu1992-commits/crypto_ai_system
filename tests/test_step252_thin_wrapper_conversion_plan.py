from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step252_thin_wrapper_plan_outputs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "wrapper_plan.json"
    csv_output = tmp_path / "wrapper_plan.csv"
    md_output = tmp_path / "wrapper_plan.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_thin_wrapper_conversion.py",
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
    assert payload["plan_type"] == "thin_wrapper_conversion_plan"
    assert payload["status"] == "PLAN_ONLY_NO_WRAPPER_CONVERSION"
    assert payload["canonical_package_root"] == "src/crypto_ai_system"
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["root_direct_imports_retired"] is True
    assert payload["root_module_count"] >= 1
    assert payload["ready_for_thin_wrapper_count"] >= 1
    assert payload["wrapper_conversion_performed"] is False
    assert payload["root_package_deletion_performed"] is False
    assert payload["import_rewrite_performed"] is False
    assert payload["live_trading_allowed"] is False
    assert payload["paper_execution_enabled"] is False
    assert payload["adapter_routing_enabled"] is False
    assert payload["rows"]


def test_step252_thin_wrapper_plan_blocks_full_conversion_when_canonical_modules_missing(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "wrapper_plan.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_thin_wrapper_conversion.py",
            "--json-output",
            str(json_output),
            "--csv-output",
            str(tmp_path / "wrapper_plan.csv"),
            "--md-output",
            str(tmp_path / "wrapper_plan.md"),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["wrapper_conversion_ready"] is False
    assert payload["wrapper_conversion_blocked"] is True
    assert payload["canonical_module_missing_count"] >= 1
    for row in payload["rows"]:
        assert row["recommended_action"] in {
            "READY_FOR_THIN_WRAPPER",
            "CANONICAL_EXPORT_REPAIR_REQUIRED",
            "CANONICAL_MODULE_MISSING",
        }
        assert row["blocker_level"] in {"LOW", "MEDIUM", "HIGH"}
