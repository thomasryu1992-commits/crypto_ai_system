from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from crypto_ai_system.backtest.paper_trading_candidate_registry import (
    STEP208_COMPATIBILITY_MODE,
    execute_paper_trading_candidate_registry,
)
from crypto_ai_system.config import load_config


def test_step208_compatibility_backfill_is_explicit_compat_stub(tmp_path: Path) -> None:
    result = execute_paper_trading_candidate_registry(tmp_path, write_output=True).to_dict()
    assert STEP208_COMPATIBILITY_MODE == "compat_stub"
    assert result["compatibility_mode"] == "compat_stub"
    assert result["compat_stub"] is True
    assert result["canonical_step208_available"] is False
    assert all(candidate["registry_id"].startswith("compat_stub_") for candidate in result["candidates"])


def test_fallback_data_profiles_are_separated_from_primary_settings() -> None:
    root = Path(__file__).resolve().parents[1]
    profile_path = root / "config" / "fallback_data_profiles.yaml"
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    cfg = load_config(root)

    assert profile_path.exists()
    assert cfg.get("fallback_data_profiles.loaded") is True
    assert cfg.get("data.fallback_profile") == profile_data["default_profile"]
    assert cfg.get("fallback_data_profiles.profiles.price_data_research.role") == "RESEARCH_BACKTEST_ONLY"
    assert cfg.get("fallback_data_profiles.profiles.price_data_research.allow_live_execution") is False
    assert cfg.get("fallback_data_profiles.profiles.sample_extended_research.allow_live_execution") is False


def test_settings_import_does_not_create_runtime_directories_or_raise_on_live_env(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    side_effect_storage = tmp_path / "must_not_be_created_storage"
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": f"{project_root}:{project_root / 'src'}",
        "STORAGE_DIR": str(side_effect_storage),
        "TRADING_MODE": "live",
        "LIVE_TRADING_ENABLED": "true",
        "LIVE_TRADING_CONFIRMATION": "wrong_phrase",
    })
    code = "import config.settings as s; print(s.STORAGE_DIR); print(hasattr(s, 'validate_live_trading_confirmation'))"
    completed = subprocess.run([sys.executable, "-c", code], cwd=project_root, env=env, text=True, capture_output=True, check=True)
    assert str(side_effect_storage) in completed.stdout
    assert "True" in completed.stdout
    assert not side_effect_storage.exists()


def test_settings_runtime_directory_creation_is_explicit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "explicit_storage"))
    import config.settings as settings_module

    reloaded = importlib.reload(settings_module)
    assert not reloaded.STORAGE_DIR.exists()
    created = reloaded.ensure_runtime_directories()
    assert reloaded.STORAGE_DIR.exists()
    assert reloaded.LATEST_DIR in created


def test_isolated_project_root_fixture_writes_artifacts_under_tmp_path(isolated_project_root: Path) -> None:
    result = execute_paper_trading_candidate_registry(isolated_project_root, write_output=True).to_dict()
    output_path = isolated_project_root / "storage/latest/step208_paper_trading_candidate_registry_latest.json"
    assert output_path.exists()
    assert str(isolated_project_root) == result["root"]
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["compatibility_mode"] == "compat_stub"
