from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_step242_manual_mapping_review_outputs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "manual_mapping_review.json"
    csv_output = tmp_path / "manual_mapping_review.csv"
    md_output = tmp_path / "manual_mapping_review.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/review_legacy_root_manual_mappings.py",
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
    assert payload["review_type"] == "legacy_root_manual_mapping_review"
    assert payload["status"] == "REVIEW_ONLY_NO_IMPORT_REWRITE"
    assert payload["canonical_package_root"] == "src/crypto_ai_system"
    assert payload["manual_mapping_input_count"] == 0
    assert payload["review_row_count"] == payload["manual_mapping_input_count"]
    assert payload["rewrite_performed"] is False
    assert payload["wrapper_conversion_performed"] is False
    assert payload["live_trading_allowed"] is False
    assert payload["paper_execution_enabled"] is False
    assert payload["adapter_routing_enabled"] is False
    assert payload["rows"] == []


def test_step242_manual_mapping_review_blocks_wrapper_conversion_until_resolved(tmp_path):
    root = Path(__file__).resolve().parents[1]
    json_output = tmp_path / "manual_mapping_review.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/review_legacy_root_manual_mappings.py",
            "--json-output",
            str(json_output),
            "--csv-output",
            str(tmp_path / "manual_mapping_review.csv"),
            "--md-output",
            str(tmp_path / "manual_mapping_review.md"),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["wrapper_conversion_blocked"] is False
    assert payload["wrapper_conversion_blocker_count"] == 0
    for row in payload["rows"]:
        assert row["recommended_action"] in {
            "READY_FOR_EXACT_CANONICAL_REWRITE_AFTER_TEST",
            "CANONICAL_DOMAIN_SYMBOL_REMAP_REQUIRED",
            "PARTIAL_CANONICAL_PORT_OR_REMAP_REQUIRED",
            "ROOT_ONLY_FEATURE_PORT_REQUIRED",
            "CANONICAL_DOMAIN_MISSING_KEEP_LEGACY",
            "PACKAGE_OR_MODULE_IMPORT_MANUAL_REVIEW",
        }
        assert row["wrapper_blocker_level"] in {"LOW", "MEDIUM", "HIGH"}
