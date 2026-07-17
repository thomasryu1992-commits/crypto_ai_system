from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_event_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep test telemetry out of the operator's event log.

    ``log_event`` writes to ``config.settings.EVENT_LOG_PATH``, so any test that
    drives a pipeline path appends to the real ``storage/logs/event_log.jsonl``.
    A single suite run added 74 rows — among them deliberately provoked failures
    (``counterfactual_settle_failed``, ``live_strategy_order_blocked``,
    ``live_position_close_failed``) that are indistinguishable from real
    incidents to anyone grepping the log for trouble.

    ``core/event_log.py`` is the only module that resolves the log path, and it
    binds the constant at import, so rebinding it there redirects every event a
    test can produce — including the fallback path, which derives from the same
    global. ``test_event_log_isolation`` guards that single-writer property,
    which is what makes this fixture sufficient.
    """
    import core.event_log as event_log

    log_path = tmp_path / "event_log.jsonl"
    monkeypatch.setattr(event_log, "EVENT_LOG_PATH", log_path)
    return log_path


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
