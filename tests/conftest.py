from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def isolated_project_root(tmp_path: Path) -> Path:
    """Minimal per-test project root for Step209~237 artifact writes.

    Tests should not write generated JSON/CSV/MD artifacts into the checked-in
    package root. The modules are imported from the test environment, while the
    runner discovery files and generated artifacts live under tmp_path.
    """
    source_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "crypto_ai_system_isolated"
    project_root.mkdir(parents=True, exist_ok=True)

    for script in source_root.glob("run_step2*_v5_*.py"):
        shutil.copy2(script, project_root / script.name)
    bootstrap = source_root / "run_step209_237_v5_chain_bootstrap.py"
    if bootstrap.exists():
        shutil.copy2(bootstrap, project_root / bootstrap.name)

    (project_root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (project_root / "storage" / "logs").mkdir(parents=True, exist_ok=True)
    (project_root / "data" / "reports").mkdir(parents=True, exist_ok=True)
    (project_root / "reports").mkdir(parents=True, exist_ok=True)
    return project_root
