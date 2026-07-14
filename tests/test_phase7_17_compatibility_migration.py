from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/lean/phase7_17_public_surface.json"


def test_phase7_17_compatibility_migration_checker() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_phase7_17_compatibility_migration.py"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PHASE7_17_COMPATIBILITY_MIGRATION_VALID" in result.stdout


def test_phase7_17_legacy_and_semantic_paths_share_exported_objects() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    legacy = importlib.import_module(
        "crypto_ai_system.validation."
        "phase7_17_final_pre_executor_review_packet"
    )
    semantic = importlib.import_module(
        "crypto_ai_system.governance.pre_executor_compat."
        "final_pre_executor_review"
    )

    names = manifest["exported_public_symbols"]
    assert names == list(semantic.__all__)

    for name in names:
        assert hasattr(legacy, name), name
        assert hasattr(semantic, name), name
        assert getattr(legacy, name) is getattr(semantic, name)


def test_phase7_17_semantic_module_uses_semantic_phase7_16_contract() -> None:
    text = (
        ROOT
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "pre_executor_compat"
        / "final_pre_executor_review.py"
    ).read_text(encoding="utf-8")

    assert (
        "crypto_ai_system.governance.pre_executor_compat."
        "operator_decision_validation"
    ) in text
    assert (
        "crypto_ai_system.validation."
        "phase7_16_operator_decision_intake_validator"
    ) not in text
