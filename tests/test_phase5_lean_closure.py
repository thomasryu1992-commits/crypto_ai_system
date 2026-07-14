from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
)
from crypto_ai_system.governance.common import (
    review_only_permission_state,
)


def test_phase5_closure_manifest_is_review_only_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[1]

    payload = json.loads(
        (
            root
            / "config"
            / "lean"
            / "phase5_lean_closure.json"
        ).read_text(encoding="utf-8")
    )

    assert payload["status"] == "PHASE5_LEAN_MERGE_CLOSED"
    assert payload["active_domain"] == "governance.approval"
    assert payload["runtime_authority"] is False
    assert payload["next_work"] == "PHASE6_READINESS_MERGE"
    assert payload["safety"]
    assert not any(payload["safety"].values())


def test_approval_and_execution_permission_states_remain_all_false() -> None:
    approval_state = review_only_permission_state()
    execution_state = default_execution_flag_state()

    assert approval_state
    assert execution_state
    assert not any(approval_state.values())
    assert not any(execution_state.values())


def test_cumulative_lean_migration_state_advances_to_phase8_without_permission_change() -> None:
    root = Path(__file__).resolve().parents[1]

    payload = json.loads(
        (
            root
            / "config"
            / "lean"
            / "lean_migration_state.json"
        ).read_text(encoding="utf-8")
    )

    assert (
        payload["completed"]["phase4_feedback"]["status"]
        == "CLOSED"
    )
    assert (
        payload["completed"]["phase5_approval"]["status"]
        == "CLOSED"
    )
    assert payload["current"]["target"] in {
        "PHASE8_SIGNED_TESTNET_EXECUTION_PREPARATION",
        "PHASE8_RUNTIME_EVIDENCE_AND_PHASE9_SINGLE_ORDER_APPROVAL_REVIEW",
    }
    assert payload["execution_permissions_changed"] is False


def test_phase5_history_is_consolidated_without_granting_permission() -> None:
    root = Path(__file__).resolve().parents[1]

    text = (
        root
        / "docs"
        / "history"
        / "PHASE5_APPROVAL_DEVELOPMENT_SUMMARY.md"
    ).read_text(encoding="utf-8")

    assert "Phase 5 active-code merge: CLOSED" in text
    assert "enable signed testnet" in text
    assert "submit, cancel, or sign an order" in text


def test_phase5_historical_build_commands_use_semantic_modules() -> None:
    root = Path(__file__).resolve().parents[1]

    for path in (root / "scripts").glob("build_phase5*.py"):
        text = path.read_text(encoding="utf-8")

        assert (
            "crypto_ai_system.validation.phase5_"
            not in text
        )

        assert "crypto_ai_system.governance." in text
