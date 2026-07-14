from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/lean/phase7_15_public_surface.json"


def test_phase7_15_compatibility_migration_checker() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_phase7_15_compatibility_migration.py"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PHASE7_15_COMPATIBILITY_MIGRATION_VALID" in result.stdout


def test_phase7_15_legacy_and_semantic_paths_share_exported_objects() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    legacy = importlib.import_module(
        "crypto_ai_system.validation."
        "phase7_15_operator_decision_intake_template"
    )
    semantic = importlib.import_module(
        "crypto_ai_system.governance.pre_executor_compat."
        "operator_decision_intake"
    )

    names = manifest["exported_public_symbols"]
    assert names == list(semantic.__all__)

    for name in names:
        assert hasattr(legacy, name), name
        assert hasattr(semantic, name), name
        assert getattr(legacy, name) is getattr(semantic, name)
