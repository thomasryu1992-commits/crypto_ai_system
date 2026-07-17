"""Test telemetry must not reach the operator's event log.

The suite drives pipeline paths and deliberately provokes failures, so without
isolation it writes rows that are indistinguishable from real incidents to anyone
grepping storage/logs/event_log.jsonl for trouble.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
import core.event_log as event_log
from core.event_log import log_event


def test_events_go_to_the_isolated_log(_isolated_event_log):
    log_event("unit_test_probe", {"marker": "isolated"})
    rows = [json.loads(line) for line in _isolated_event_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["event_type"] for r in rows] == ["unit_test_probe"]


def test_the_real_event_log_is_never_the_target():
    """The autouse fixture is what stands between the suite and the real log, so
    assert on the rebound global rather than trusting it stayed rebound."""
    assert Path(event_log.EVENT_LOG_PATH) != Path(settings.EVENT_LOG_PATH)


def test_real_event_log_does_not_grow():
    real = Path(settings.EVENT_LOG_PATH)
    before = real.stat().st_size if real.exists() else 0
    log_event("unit_test_probe", {"marker": "must_not_land_in_the_real_log"})
    after = real.stat().st_size if real.exists() else 0
    assert after == before


def _sources() -> list[Path]:
    skip = {".git", "__pycache__", "archive", ".venv", "tests"}
    return [
        path
        for path in ROOT.rglob("*.py")
        if not skip & set(path.parts) and path.name not in {"settings.py", "conftest.py"}
    ]


def test_nothing_builds_the_log_path_itself():
    """settings.py owns the filename. Collectors used to rebuild it by hand
    (``paths['logs'] / 'event_log.jsonl'``), which bypassed both this fixture and
    log_event's row shape — fail here rather than quietly resuming pollution."""
    hardcoded = [
        p.relative_to(ROOT).as_posix()
        for p in _sources()
        if "event_log.jsonl" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert hardcoded == []


def test_only_log_event_resolves_the_path():
    """Isolation rebinds one global, so it is sufficient only while one module
    reads it."""
    readers = [
        p.relative_to(ROOT).as_posix()
        for p in _sources()
        if "EVENT_LOG_PATH" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert readers == ["core/event_log.py"]
