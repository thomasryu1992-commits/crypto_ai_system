from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def test_agent_import_manifest_is_package_boundary_only():
    import_manifest = json.loads((ROOT / "agent_import_manifest.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "agent_manifest.json").read_text(encoding="utf-8"))
    assert import_manifest["agent_id"] == "crypto_ai_system"
    assert import_manifest["boundary"] == "crypto_ai_system_zip_only"
    assert import_manifest["expected_zip_top_level_dir"] == "crypto_ai_system"
    assert import_manifest["entrypoint"] == "python scripts/run_command.py"
    assert manifest["agent_os_import"]["launcher_import_manager_implemented_here"] is False
    assert manifest["agent_os_import"]["telegram_router_implemented_here"] is False
    assert import_manifest["safe_defaults"]["execution_permission_granted"] is False
    assert import_manifest["safe_defaults"]["stage_transition_allowed"] is False
    assert "agents_zip_inbox_scan" in import_manifest["launcher_owned_responsibilities"]
    assert "standard_run_command_entrypoint" in import_manifest["package_owned_responsibilities"]


def test_validate_agent_os_import_package_directory_returns_json():
    proc = subprocess.run([sys.executable, "scripts/validate_agent_os_import_package.py"], cwd=ROOT, text=True, capture_output=True, timeout=60)
    payload = _last_json(proc.stdout)
    assert proc.returncode == 0
    assert payload["success"] is True
    assert payload["status"] == "passed"
    assert payload["checks"]["package_contract_supported"] == "passed"
    assert payload["checks"]["launcher_not_implemented_here"] == "passed"
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False


def test_release_builder_can_create_importable_single_top_level_zip(tmp_path: Path):
    proc = subprocess.run([sys.executable, "scripts/build_agent_os_release.py", "--output-dir", str(tmp_path), "--skip-self-test"], cwd=ROOT, text=True, capture_output=True, timeout=120)
    payload = _last_json(proc.stdout)
    assert proc.returncode == 0
    assert payload["success"] is True
    assert payload["status"] == "release_built"
    assert payload["boundary"] == "crypto_ai_system_zip_only"
    assert payload["import_package_validation_passed"] is True
    assert payload["expected_zip_top_level_dir"] == "crypto_ai_system"
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
    zip_path = Path(payload["zip_path"])
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        top_levels = {name.split("/", 1)[0] for name in names if name}
        assert top_levels == {"crypto_ai_system"}
        assert "crypto_ai_system/agent_manifest.json" in names
        assert "crypto_ai_system/agent_import_manifest.json" in names
        assert "crypto_ai_system/config/agent_os_registry_fixture.json" not in names
        assert "crypto_ai_system/scripts/simulate_agent_os_import_manager.py" not in names
        assert "crypto_ai_system/scripts/simulate_agent_os_local_launcher_import.py" not in names
