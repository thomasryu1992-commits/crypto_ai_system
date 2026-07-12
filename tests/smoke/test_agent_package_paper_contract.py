import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def _run_command(tmp_path: Path, *args: str) -> tuple[dict, str, dict]:
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
    sidecar = Path(payload["artifact_metadata_path"])
    if not sidecar.is_absolute():
        sidecar = ROOT / sidecar
    assert artifact.exists()
    assert sidecar.exists()
    return payload, artifact.read_text(encoding="utf-8"), json.loads(sidecar.read_text(encoding="utf-8"))


def test_paper_command_emits_review_only_paper_simulation_contract(tmp_path):
    payload, report, sidecar = _run_command(tmp_path, "--command", "paper", "--dry-run", "--job-id", "job-paper-001")

    assert payload["success"] is True
    assert payload["command"] == "paper"
    assert payload["artifact_type"] == "paper_simulation"
    assert payload["artifact_format"] == "markdown"
    assert payload["paper_simulation_contract_version"] == "paper_simulation_review_v1"
    assert len(payload["paper_session_id"]) == 24
    assert len(payload["paper_run_id"]) == 24
    assert len(payload["simulation_scope_id"]) == 24
    assert len(payload["source_artifact_sha256"]) == 64
    assert payload["approval_required"] is True
    assert payload["approval_satisfied_for_local_launcher_command"] is True
    assert payload["approval_grants_real_execution"] is False
    assert payload["paper_order_submission_performed"] is False
    assert payload["paper_execution_adapter_called"] is False
    assert payload["order_intent_created"] is False
    assert payload["review_only"] is True
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
    assert payload["live_candidate_eligible"] is False
    assert payload["signed_testnet_candidate_eligible"] is False
    assert payload["order_endpoint_called"] is False
    assert payload["order_status_endpoint_called"] is False
    assert payload["cancel_endpoint_called"] is False
    assert payload["exchange_adapter_called"] is False
    assert payload["signed_request_created"] is False
    assert payload["secret_value_accessed"] is False
    assert payload["runtime_settings_mutated"] is False

    assert sidecar["paper_simulation_contract_version"] == "paper_simulation_review_v1"
    assert sidecar["paper_order_submission_performed"] is False
    assert sidecar["paper_execution_adapter_called"] is False
    assert sidecar["execution_permission_granted"] is False
    assert sidecar["stage_transition_allowed"] is False

    assert "## Paper Simulation Contract" in report
    assert f"paper_session_id: {payload['paper_session_id']}" in report
    assert f"paper_run_id: {payload['paper_run_id']}" in report
    assert "paper_simulation_contract_version: paper_simulation_review_v1" in report
    assert "approval_required: true" in report
    assert "approval_grants_real_execution: false" in report
    assert "## Execution Boundary" in report
    assert "It does not create a real order intent" in report
    assert "It does not submit, poll, cancel, or reconcile exchange orders" in report
    assert "execution_permission_granted: false" in report
    assert "stage_transition_allowed: false" in report
    assert "order_endpoint_called: false" in report
    assert "secret_value_accessed: false" in report


def test_paper_without_approval_is_blocked_when_not_dry_run(tmp_path):
    proc = subprocess.run(
        [sys.executable, "scripts/run_command.py", "--command", "paper", "--output-dir", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    payload = _last_json(proc.stdout)
    assert proc.returncode == 5
    assert payload["success"] is False
    assert payload["status"] == "blocked"
    assert "requires approval" in payload["error_message"]
