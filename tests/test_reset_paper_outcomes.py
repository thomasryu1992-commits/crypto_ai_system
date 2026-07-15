"""Tests for the paper-outcome reset helper (tmp files, no real storage)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.reset_paper_outcomes import reset_target


def test_dry_run_counts_without_changing(tmp_path):
    f = tmp_path / "reg.jsonl"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    result = reset_target({"name": "reg", "path": f, "kind": "jsonl"}, None)
    assert result["records"] == 3
    assert result["backed_up"] is False
    assert f.read_text(encoding="utf-8") == "a\nb\nc\n"  # untouched


def test_apply_backs_up_and_clears_jsonl(tmp_path):
    f = tmp_path / "reg.jsonl"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    backup = tmp_path / "backup"
    result = reset_target({"name": "reg", "path": f, "kind": "jsonl"}, backup)
    assert result["records"] == 3
    assert result["backed_up"] is True
    assert f.read_text(encoding="utf-8") == ""  # cleared
    assert (backup / "reg.jsonl").read_text(encoding="utf-8") == "a\nb\nc\n"  # preserved


def test_apply_clears_json_list(tmp_path):
    f = tmp_path / "paper_trades.json"
    f.write_text('[{"x": 1}, {"x": 2}]', encoding="utf-8")
    result = reset_target({"name": "paper_trades", "path": f, "kind": "json_list"}, tmp_path / "b")
    assert result["records"] == 2
    assert json.loads(f.read_text(encoding="utf-8")) == []


def test_apply_resets_paper_state(tmp_path):
    f = tmp_path / "paper_state.json"
    f.write_text('{"active_position": {"symbol": "BTCUSDT"}}', encoding="utf-8")
    reset_target({"name": "paper_state", "path": f, "kind": "paper_state"}, tmp_path / "b")
    assert json.loads(f.read_text(encoding="utf-8")) == {
        "active_position": None,
        "closed_trades": [],
    }


def test_missing_file_is_zero(tmp_path):
    f = tmp_path / "nope.jsonl"
    result = reset_target({"name": "nope", "path": f, "kind": "jsonl"}, tmp_path / "b")
    assert result["records"] == 0
    assert result["backed_up"] is False
