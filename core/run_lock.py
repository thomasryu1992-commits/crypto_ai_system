"""Single-runner lock for the pipeline (QA fix).

The `storage/latest/` JSON handoff has no cycle-id binding, so two overlapping
runs (the hourly Scheduled Task + a manual `py run_pipeline.py`) can execute
each other's artifacts — run B overwrites `latest_trade_decision.json` between
run A's write and read. This OS-level lock makes overlap impossible: the second
runner refuses loudly instead of interleaving.

The lock is held on an open file handle (msvcrt on Windows, fcntl elsewhere),
so it dies with the process — a crashed run never leaves a stale lock behind.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class PipelineAlreadyRunning(RuntimeError):
    """Another process holds the pipeline lock — refuse to interleave."""


def _try_lock(handle) -> bool:
    try:
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    except ImportError:
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False


def _unlock(handle) -> None:
    try:
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    except ImportError:
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


@contextmanager
def pipeline_run_lock(lock_path: Path | None = None) -> Iterator[None]:
    """Hold the exclusive pipeline lock for the duration of one run.

    Raises :class:`PipelineAlreadyRunning` immediately (non-blocking) when
    another process holds it — the caller reports and exits rather than
    running a second cycle against shared storage.
    """
    if lock_path is None:
        from config.settings import STORAGE_DIR

        lock_path = Path(STORAGE_DIR) / "pipeline.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    try:
        handle.seek(0)  # msvcrt locks a byte range at the current position
        if not _try_lock(handle):
            handle.close()
            raise PipelineAlreadyRunning(
                f"another pipeline run holds {lock_path} — refusing to overlap"
            )
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
        except OSError:
            pass  # the PID note is informational; the lock is the handle itself
        try:
            yield
        finally:
            _unlock(handle)
            handle.close()
    except PipelineAlreadyRunning:
        raise
