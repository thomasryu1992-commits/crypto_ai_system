"""Dual-config parsing must agree (QA fix): same env string, same answer in
both halves; garbage numerics default instead of crashing; load_config(".")
anchors at the repo root, not the process cwd."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config.settings import env_bool
from crypto_ai_system.config import _to_bool, _to_float, _to_int, load_config


def test_bool_vocabulary_matches_env_bool(monkeypatch):
    for token in ("1", "true", "yes", "y", "on", "enabled", "TRUE", "Enabled"):
        monkeypatch.setenv("QA_BOOL_PROBE", token)
        assert _to_bool(token) is True, token
        assert env_bool("QA_BOOL_PROBE") is True, token
    for token in ("0", "false", "off", "no", "disabled", "garbage", ""):
        monkeypatch.setenv("QA_BOOL_PROBE", token)
        assert _to_bool(token) is False, token
        # env_bool("") falls to its default (False here) — same effective answer.
        assert env_bool("QA_BOOL_PROBE") is False, token


def test_numeric_garbage_defaults_instead_of_crashing():
    assert _to_int("500.0", 100) == 500  # env_int semantics: float strings OK
    assert _to_int("500 bars", 100) == 100
    assert _to_int(None, 100) == 100
    assert _to_float("2.5x", 9.9) == 9.9
    assert _to_float("2.5", 9.9) == 2.5


def test_malformed_default_limit_env_does_not_crash_load_config(monkeypatch):
    monkeypatch.setenv("DEFAULT_LIMIT", "500 bars")
    cfg = load_config(".")
    assert cfg.get("data.limit") == 500  # default, not a ValueError


def test_load_config_dot_anchors_at_repo_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # simulate Task Scheduler without "Start in"
    cfg = load_config(".")
    assert cfg.root == ROOT
    assert (cfg.root / "config" / "settings.yaml").exists()
