import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def _run_command(tmp_path: Path, *args: str) -> tuple[dict, str]:
    proc = subprocess.run(
        [sys.executable, "scripts/run_command.py", *args, "--output-dir", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = _last_json(proc.stdout)
    artifact = Path(payload["artifact_path"])
    if not artifact.is_absolute():
        artifact = ROOT / artifact
    assert artifact.exists()
    return payload, artifact.read_text(encoding="utf-8")


def test_backtest_command_emits_review_only_backtest_contract(tmp_path):
    payload, report = _run_command(tmp_path, "--command", "backtest", "--dry-run", "--job-id", "job-backtest-001")
    assert payload["success"] is True
    assert payload["command"] == "backtest"
    assert payload["artifact_type"] == "backtest"
    assert payload["artifact_format"] == "markdown"
    assert payload["backtest_contract_version"] == "backtest_review_v1"
    assert len(payload["backtest_id"]) == 24
    assert len(payload["source_artifact_sha256"]) == 64
    assert payload["historical_data_only"] is True
    assert payload["review_only"] is True
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
    assert payload["live_candidate_eligible"] is False
    assert payload["signed_testnet_candidate_eligible"] is False

    assert "## Backtest Contract" in report
    assert f"backtest_id: {payload['backtest_id']}" in report
    assert "backtest_contract_version: backtest_review_v1" in report
    assert "historical_data_only: true" in report
    assert "No live, signed testnet, or paper execution evidence" in report
    assert "execution_permission_granted: false" in report
    assert "stage_transition_allowed: false" in report
    assert "order_endpoint_called: false" in report
    assert "secret_value_accessed: false" in report


def test_feedback_command_emits_review_only_feedback_contract(tmp_path):
    payload, report = _run_command(tmp_path, "--command", "feedback", "--dry-run", "--job-id", "job-feedback-001")
    assert payload["success"] is True
    assert payload["command"] == "feedback"
    assert payload["artifact_type"] == "feedback"
    assert payload["artifact_format"] == "markdown"
    assert payload["feedback_contract_version"] == "feedback_review_v1"
    assert len(payload["feedback_cycle_id"]) == 24
    assert len(payload["outcome_review_id"]) == 24
    assert len(payload["source_artifact_sha256"]) == 64
    assert payload["runtime_mutation_allowed"] is False
    assert payload["review_only"] is True
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
    assert payload["live_candidate_eligible"] is False
    assert payload["signed_testnet_candidate_eligible"] is False

    assert "## Feedback Contract" in report
    assert f"feedback_cycle_id: {payload['feedback_cycle_id']}" in report
    assert f"outcome_review_id: {payload['outcome_review_id']}" in report
    assert "feedback_contract_version: feedback_review_v1" in report
    assert "runtime_mutation_allowed: false" in report
    assert "Feedback must not directly change score weights" in report
    assert "execution_permission_granted: false" in report
    assert "stage_transition_allowed: false" in report
    assert "order_endpoint_called: false" in report
    assert "secret_value_accessed: false" in report
