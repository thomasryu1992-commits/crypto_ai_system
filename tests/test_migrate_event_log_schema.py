"""The migration rewrites the operator's event log in place, so its behaviour is
pinned here: it must repair the legacy rows, preserve everything else byte for
byte, and never guess at a timestamp it cannot bound."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import migrate_event_log_schema as mig


def _canonical(event_type: str, timestamp: str):
    return {"timestamp": timestamp, "event_type": event_type, "severity": "INFO", "payload": {"a": 1}}


def _legacy(type_: str = "data_collect_fallback", **extra):
    """A row as the bypassing collector wrote it: a 'type' tag, no envelope."""
    return {"type": type_, "source": "price_data", "reason": "boom", **extra}


def _write(path: Path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _read(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run(path: Path, *args):
    return mig.main([*args, "--path", str(path)])


# -- classification -----------------------------------------------------------

def test_only_the_bypassing_writers_rows_are_legacy():
    assert mig.is_legacy(_legacy()) is True
    assert mig.is_legacy(_canonical("x", "2026-07-14T04:13:06+00:00")) is False
    # Missing event_type for some other reason is not ours to guess at.
    assert mig.is_legacy({"payload": {}}) is False
    assert mig.is_legacy({"type": 42}) is False


# -- migration ----------------------------------------------------------------

def test_legacy_row_becomes_a_canonical_envelope(tmp_path):
    log = tmp_path / "event_log.jsonl"
    _write(log, [_canonical("research_cycle_completed", "2026-07-14T04:13:06+00:00"), _legacy()])
    assert _run(log, "--confirm") == 0

    rows = _read(log)
    assert len(rows) == 2
    migrated = rows[1]
    assert migrated["event_type"] == "data_collect_fallback"
    assert migrated["severity"] == "INFO"
    # The tag becomes the event type; everything else becomes payload.
    assert migrated["payload"] == {"source": "price_data", "reason": "boom"}
    assert "type" not in migrated


def test_timestamp_is_taken_from_the_preceding_row_and_marked(tmp_path):
    log = tmp_path / "event_log.jsonl"
    _write(log, [
        _canonical("research_decision_created", "2026-07-14T04:13:06+00:00"),
        _legacy(),
        _canonical("research_decision_created", "2026-07-14T04:13:08+00:00"),
    ])
    _run(log, "--confirm")

    migrated = _read(log)[1]
    assert migrated["timestamp"] == "2026-07-14T04:13:06+00:00"
    # Nobody should later mistake an inferred time for a recorded one.
    assert migrated["timestamp_inferred"] is True
    assert migrated["schema_migrated"] is True


def test_a_row_with_no_preceding_timestamp_is_left_alone(tmp_path):
    """Only possible at the head of the file. Guessing is worse than reporting."""
    log = tmp_path / "event_log.jsonl"
    _write(log, [_legacy(), _canonical("later", "2026-07-14T04:13:08+00:00")])
    _run(log, "--confirm")

    rows = _read(log)
    assert rows[0] == _legacy()  # untouched
    assert "schema_migrated" not in rows[0]


def test_canonical_rows_survive_untouched(tmp_path):
    log = tmp_path / "event_log.jsonl"
    original = [
        _canonical("research_cycle_completed", "2026-07-14T04:13:06+00:00"),
        _legacy(),
        _canonical("order_execution_attempted", "2026-07-14T04:13:08+00:00"),
    ]
    _write(log, original)
    _run(log, "--confirm")

    rows = _read(log)
    assert rows[0] == original[0]
    assert rows[2] == original[2]


def test_row_order_is_preserved(tmp_path):
    log = tmp_path / "event_log.jsonl"
    _write(log, [
        _canonical("a", "2026-07-14T04:13:01+00:00"),
        _legacy("data_collect_fallback"),
        _legacy("data_collect_enrichment_skipped"),
        _canonical("b", "2026-07-14T04:13:09+00:00"),
    ])
    _run(log, "--confirm")

    assert [r["event_type"] for r in _read(log)] == [
        "a", "data_collect_fallback", "data_collect_enrichment_skipped", "b",
    ]


# -- safety -------------------------------------------------------------------

def test_dry_run_changes_nothing(tmp_path):
    log = tmp_path / "event_log.jsonl"
    rows = [_canonical("a", "2026-07-14T04:13:06+00:00"), _legacy()]
    _write(log, rows)
    before = log.read_text(encoding="utf-8")

    assert _run(log) == 0
    assert log.read_text(encoding="utf-8") == before


def test_apply_backs_up_first(tmp_path, monkeypatch):
    log = tmp_path / "event_log.jsonl"
    _write(log, [_canonical("a", "2026-07-14T04:13:06+00:00"), _legacy()])
    before = log.read_text(encoding="utf-8")
    monkeypatch.setattr(mig, "ROOT", tmp_path)

    _run(log, "--confirm")

    backups = list((tmp_path / "storage" / "backup").glob("event_log_migration_*/event_log.jsonl"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == before


def test_unparseable_lines_are_left_in_place(tmp_path):
    log = tmp_path / "event_log.jsonl"
    log.write_text(
        json.dumps(_canonical("a", "2026-07-14T04:13:06+00:00")) + "\nnot json at all\n",
        encoding="utf-8",
    )
    assert _run(log, "--confirm") == 0
    # Nothing to migrate, so the file is not rewritten and the junk line survives.
    assert "not json at all" in log.read_text(encoding="utf-8")


def test_migration_is_idempotent(tmp_path):
    log = tmp_path / "event_log.jsonl"
    _write(log, [_canonical("a", "2026-07-14T04:13:06+00:00"), _legacy()])
    _run(log, "--confirm")
    once = log.read_text(encoding="utf-8")
    _run(log, "--confirm")
    assert log.read_text(encoding="utf-8") == once


def test_missing_log_is_not_an_error(tmp_path):
    assert _run(tmp_path / "nope.jsonl", "--confirm") == 0


# -- verify -------------------------------------------------------------------

def test_verify_fails_before_and_passes_after(tmp_path):
    log = tmp_path / "event_log.jsonl"
    _write(log, [_canonical("a", "2026-07-14T04:13:06+00:00"), _legacy()])
    assert _run(log, "--verify") == 1
    _run(log, "--confirm")
    assert _run(log, "--verify") == 0
