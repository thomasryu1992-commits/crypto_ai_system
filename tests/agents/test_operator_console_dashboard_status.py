from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from crypto_ai_system.ops.operator_dashboard_status import (
    FORBIDDEN_UI_ACTIONS,
    SAFE_REVIEW_ONLY_SCRIPTS,
    build_operator_dashboard_status,
    persist_operator_dashboard_status,
)

ROOT = Path(__file__).resolve().parents[2]


def test_operator_dashboard_status_is_review_only_and_disabled() -> None:
    status = build_operator_dashboard_status(ROOT)

    assert status["artifact_type"] == "operator_dashboard_status"
    assert status["review_only"] is True
    assert status["frontend_authority"] == "read_only_report_viewer"
    assert status["runtime_mutation_allowed"] is False
    assert status["order_submission_allowed"] is False
    assert status["secret_input_allowed"] is False
    assert status["settings_edit_allowed"] is False
    assert status["executor_enable_allowed"] is False
    assert status["execution_flags_all_disabled"] is True
    assert status["unsafe_true_execution_flags"] == []

    for action in FORBIDDEN_UI_ACTIONS:
        assert status["disabled_controls"][action]["enabled"] is False

    assert status["approval_and_blockers"]["order_submission_authorized"] is False
    assert status["approval_and_blockers"]["actual_order_submission_performed"] is False


def test_operator_dashboard_status_persists_report() -> None:
    status = persist_operator_dashboard_status(ROOT)
    out = ROOT / "storage" / "latest" / "operator_dashboard_status.json"
    handoff = ROOT / "storage" / "latest" / "OPERATOR_DASHBOARD_STATUS_HANDOFF_REVIEW_ONLY.md"

    assert out.exists()
    assert handoff.exists()
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["operator_dashboard_status_sha256"] == status["operator_dashboard_status_sha256"]
    assert saved["execution_flags_all_disabled"] is True


def test_operator_console_has_no_secret_input_or_order_submit_controls() -> None:
    console = (ROOT / "frontend" / "operator_console.py").read_text(encoding="utf-8")

    forbidden_snippets = [
        "st.text_input(",
        "st.number_input(",
        "st.file_uploader(",
        "submit_order(",
        "place_order(",
        "cancel_order(",
        "enable_executor(",
        "enable_live(",
        "enable_testnet(",
    ]
    for snippet in forbidden_snippets:
        assert snippet not in console

    assert "SAFE_REVIEW_ONLY_SCRIPTS" in console
    assert "Review-only" in console or "review-only" in console


def test_operator_console_script_allowlist_excludes_runtime_submit_and_endpoint_enablers() -> None:
    serialized = json.dumps(SAFE_REVIEW_ONLY_SCRIPTS, sort_keys=True)
    forbidden = [
        "submit_runtime_action",
        "enable_executor",
        "enable_live",
        "enable_testnet",
        "place_order",
        "cancel_order_runtime",
    ]
    for token in forbidden:
        assert token not in serialized

    for rel_path in SAFE_REVIEW_ONLY_SCRIPTS.values():
        assert rel_path.startswith("scripts/")
        assert (ROOT / rel_path).exists() or rel_path == "scripts/build_operator_dashboard_status.py"


def test_build_operator_dashboard_status_script_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_operator_dashboard_status.py")],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "operator_dashboard_status" in result.stdout
    assert "execution_flags_all_disabled= True" in result.stdout
