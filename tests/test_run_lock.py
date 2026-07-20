"""Pipeline single-runner lock (QA fix): overlapping runs must refuse, not
interleave their storage/latest artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.run_lock import PipelineAlreadyRunning, pipeline_run_lock


def test_lock_is_exclusive_while_held(tmp_path):
    lock = tmp_path / "pipeline.lock"
    with pipeline_run_lock(lock):
        with pytest.raises(PipelineAlreadyRunning):
            with pipeline_run_lock(lock):
                pytest.fail("second holder must never enter")


def test_lock_is_reacquirable_after_release(tmp_path):
    lock = tmp_path / "pipeline.lock"
    with pipeline_run_lock(lock):
        pass
    with pipeline_run_lock(lock):
        pass  # no exception: the first release freed it


def test_lock_released_even_when_body_raises(tmp_path):
    lock = tmp_path / "pipeline.lock"
    with pytest.raises(ValueError):
        with pipeline_run_lock(lock):
            raise ValueError("cycle blew up")
    with pipeline_run_lock(lock):
        pass  # still acquirable
