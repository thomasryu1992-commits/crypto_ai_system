from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_launcher_owned_artifacts_are_not_in_crypto_package_boundary():
    removed = [
        "scripts/simulate_agent_os_import_manager.py",
        "scripts/simulate_agent_os_local_launcher_import.py",
        "scripts/agent_os_registry_handshake.py",
        "scripts/emulate_agent_os_telegram_run.py",
        "config/agent_os_registry_fixture.json",
        "examples/agent_os_import",
        "examples/agent_os_local_launcher",
    ]
    for rel in removed:
        assert not (ROOT / rel).exists(), rel


def test_manifest_declares_package_boundary_not_launcher_implementation():
    manifest = json.loads((ROOT / "agent_manifest.json").read_text(encoding="utf-8"))
    contract = manifest["agent_package_contract"]
    assert contract["boundary"] == "crypto_ai_system_zip_only"
    assert contract["execution_permission_granted"] is False
    assert contract["stage_transition_allowed"] is False
    assert "0_IMPORT_ZIP.bat" in contract["launcher_owned_responsibilities"]
    assert "standard_run_command_entrypoint" in contract["package_owned_responsibilities"]
    assert manifest["agent_os_import"]["launcher_import_manager_implemented_here"] is False
    assert manifest["agent_os_import"]["telegram_router_implemented_here"] is False


def test_readme_and_import_docs_do_not_reference_removed_launcher_scripts():
    forbidden_tokens = [
        "scripts/agent_os_registry_handshake.py",
        "scripts/emulate_agent_os_telegram_run.py",
        "scripts/simulate_agent_os_import_manager.py",
        "scripts/simulate_agent_os_local_launcher_import.py",
        "config/agent_os_registry_fixture.json",
        "examples/telegram",
        "examples/agent_os_import",
        "examples/agent_os_local_launcher",
    ]
    docs = [
        ROOT / "README_AGENT.md",
        ROOT / "docs" / "AGENT_OS_IMPORT_COMPATIBILITY.md",
        ROOT / "docs" / "AGENT_PACKAGE_BOUNDARY.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{token} leaked into {path}"
