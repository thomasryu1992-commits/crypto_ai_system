"""Registry append hardening (QA fix): O(1) tail validation keeps the torn-line
fail-closed contract without re-parsing the whole file per append; rotation
archives oversized write-only registries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.registry.base_registry import (
    RegistryIntegrityError,
    append_registry_record,
    load_registry_records,
    rotate_registry_if_large,
)


def _append(path, record):
    return append_registry_record(path, record, registry_name="qa_test_registry")


def test_append_then_load_round_trips(tmp_path):
    path = tmp_path / "reg.jsonl"
    _append(path, {"value": 1})
    _append(path, {"value": 2})
    rows = load_registry_records(path)
    assert [r["value"] for r in rows] == [1, 2]


def test_torn_tail_fails_closed_on_append(tmp_path):
    path = tmp_path / "reg.jsonl"
    _append(path, {"value": 1})
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"value": 2, "torn')  # crash mid-append: no newline
    with pytest.raises(RegistryIntegrityError):
        _append(path, {"value": 3})


def test_garbage_tail_line_fails_closed(tmp_path):
    path = tmp_path / "reg.jsonl"
    _append(path, {"value": 1})
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json at all\n")
    with pytest.raises(RegistryIntegrityError):
        _append(path, {"value": 2})


def test_append_does_not_scan_the_whole_file(tmp_path, monkeypatch):
    # Damage an EARLY line: the O(1) tail check must not see it (full readers
    # still do), so the append succeeds — proving no full-file re-parse.
    path = tmp_path / "reg.jsonl"
    _append(path, {"value": 1})
    _append(path, {"value": 2})
    text = path.read_text(encoding="utf-8").splitlines()
    text[0] = "damaged-first-line"
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    _append(path, {"value": 3})  # tail is intact -> append allowed
    with pytest.raises(RegistryIntegrityError):
        load_registry_records(path)  # full read still fails closed


def test_rotation_archives_and_restarts(tmp_path):
    path = tmp_path / "reg.jsonl"
    _append(path, {"value": 1})
    size = path.stat().st_size
    archive = rotate_registry_if_large(path, max_bytes=size)  # at threshold -> rotate
    assert archive is not None and archive.exists()
    assert not path.exists()
    _append(path, {"value": 2})  # fresh file
    assert [r["value"] for r in load_registry_records(path)] == [2]
    assert [r["value"] for r in load_registry_records(archive)] == [1]


def test_rotation_is_a_noop_below_threshold(tmp_path):
    path = tmp_path / "reg.jsonl"
    _append(path, {"value": 1})
    assert rotate_registry_if_large(path, max_bytes=10 * 1024 * 1024) is None
    assert path.exists()
