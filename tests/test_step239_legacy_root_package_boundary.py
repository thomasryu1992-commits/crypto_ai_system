from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


def test_step239_legacy_root_init_metadata_present():
    for domain in ("execution", "trading", "research"):
        module = importlib.import_module(domain)
        assert getattr(module, "LEGACY_COMPATIBILITY_PACKAGE", None) is True
        assert getattr(module, "CANONICAL_PACKAGE", None) == f"crypto_ai_system.{domain}"
        assert getattr(module, "MIGRATION_STATUS", None) == "wrapper_migration_pending"


def test_step239_legacy_package_audit_script_runs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "legacy_audit.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_legacy_root_packages.py",
            "--output",
            str(output),
            "--fail-on-unmarked-legacy-init",
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["canonical_package_root"] == "src/crypto_ai_system"
    assert payload["root_packages_allowed_only_as_compatibility"] is True
    assert payload["status"] == "MIGRATION_PENDING"
    domains = {row["domain"]: row for row in payload["inventory"]}
    for domain in ("execution", "trading", "research"):
        assert domains[domain]["root_exists"] is True
        assert domains[domain]["canonical_exists"] is True
        assert domains[domain]["root_init_marked_compatibility"] is True
        assert domains[domain]["migration_status"] == "wrapper_migration_pending"
