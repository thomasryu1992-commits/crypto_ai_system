from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
)


def test_phase4_closure_manifest_is_review_only_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "config" / "lean" / "phase4_lean_closure.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "PHASE4_LEAN_MERGE_CLOSED"
    assert payload["active_domain"] == "feedback"
    assert payload["runtime_authority"] is False
    assert payload["next_work"] == "PHASE5_APPROVAL_MERGE"
    assert payload["safety"]
    assert not any(payload["safety"].values())


def test_runtime_disabled_registry_remains_all_false() -> None:
    state = default_execution_flag_state()
    assert state
    assert not any(state.values())


def test_phase4_history_is_consolidated_without_granting_permission() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "docs"
        / "history"
        / "PHASE4_FEEDBACK_DEVELOPMENT_SUMMARY.md"
    ).read_text(encoding="utf-8")

    assert "Phase 4 active-code merge: CLOSED" in text
    assert "enable signed testnet" in text
    assert "submit, cancel, or sign orders" in text


def test_phase4_old_build_commands_use_semantic_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"

    for path in scripts.glob("build_phase4*.py"):
        text = path.read_text(encoding="utf-8")
        assert "crypto_ai_system.validation.phase4_" not in text
        assert "crypto_ai_system.feedback." in text
