from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step243_canonical_port_plan_outputs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "canonical_port_plan.json"
    csv_output = tmp_path / "canonical_port_plan.csv"
    md_output = tmp_path / "canonical_port_plan.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_canonical_ports_for_root_only_features.py",
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
    assert payload["plan_type"] == "canonical_port_plan_for_root_only_legacy_features"
    assert payload["status"] == "PLAN_ONLY_NO_CODE_PORT"
    assert payload["canonical_package_root"] == "src/crypto_ai_system"
    assert payload["root_only_input_count"] == 0
    assert payload["port_group_count"] == 0
    assert payload["total_import_reference_count"] >= payload["port_group_count"]
    assert payload["port_performed"] is False
    assert payload["import_rewrite_performed"] is False
    assert payload["wrapper_conversion_performed"] is False
    assert payload["wrapper_conversion_blocked"] is False
    assert payload["live_trading_allowed"] is False
    assert payload["paper_execution_enabled"] is False
    assert payload["adapter_routing_enabled"] is False
    assert payload["groups"] == []


def test_step243_port_groups_are_module_grouped(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "canonical_port_plan.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_canonical_ports_for_root_only_features.py",
            "--json-output",
            str(json_output),
            "--csv-output",
            str(tmp_path / "canonical_port_plan.csv"),
            "--md-output",
            str(tmp_path / "canonical_port_plan.md"),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    legacy_modules = [group["legacy_module"] for group in payload["groups"]]
    assert len(legacy_modules) == len(set(legacy_modules))
    for group in payload["groups"]:
        assert group["proposed_canonical_module"].startswith("crypto_ai_system.")
        assert group["proposed_port_action"] in {
            "EXTEND_EXISTING_CANONICAL_MODULE",
            "CREATE_CANONICAL_MODULE_FROM_ROOT_LEGACY",
        }
        assert group["priority"] in {"LOW", "MEDIUM", "HIGH"}
        assert group["wrapper_conversion_blocker"] is True
