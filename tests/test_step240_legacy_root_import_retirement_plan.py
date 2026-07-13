from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step240_import_retirement_plan_outputs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "retirement_plan.json"
    csv_output = tmp_path / "retirement_plan.csv"
    md_output = tmp_path / "retirement_plan.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_legacy_root_import_retirement.py",
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
    assert payload["plan_type"] == "legacy_root_import_retirement_plan"
    assert payload["status"] == "PLAN_ONLY_NO_IMPORT_REWRITE"
    assert payload["canonical_package_root"] == "src/crypto_ai_system"
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["rewrite_performed"] is False
    assert payload["wrapper_conversion_performed"] is False
    assert payload["live_trading_allowed"] is False
    assert payload["paper_execution_enabled"] is False
    assert payload["adapter_routing_enabled"] is False
    assert payload["rows"] == []


def test_step240_plan_contains_only_known_domains(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "retirement_plan.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_legacy_root_import_retirement.py",
            "--json-output",
            str(json_output),
            "--csv-output",
            str(tmp_path / "retirement_plan.csv"),
            "--md-output",
            str(tmp_path / "retirement_plan.md"),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    allowed = {"execution", "trading", "research"}
    assert set(payload["findings_by_domain"]).issubset(allowed)
    for row in payload["rows"]:
        assert row["domain"] in allowed
        assert row["canonical_module"].startswith("crypto_ai_system.")
        assert row["suggested_action"] in {
            "READY_FOR_CANONICAL_IMPORT_REWRITE",
            "READY_FOR_PACKAGE_LEVEL_CANONICAL_IMPORT_REWRITE",
            "MANUAL_MAPPING_REQUIRED",
            "KEEP_LEGACY_TEMPORARY",
        }
