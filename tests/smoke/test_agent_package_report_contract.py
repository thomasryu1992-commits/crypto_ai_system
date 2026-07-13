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
    return payload, artifact.read_text(encoding="utf-8")


def test_daily_report_contract_v2_contains_safety_metadata(tmp_path):
    payload, report = _run_command(tmp_path, "--command", "daily", "--dry-run", "--job-id", "job-daily-001")
    assert payload["artifact_type"] == "report"
    assert payload["artifact_format"] == "markdown"
    assert payload["review_only"] is True
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
    assert "artifact_contract_version: agent_report_v2" in report
    assert "review_only: true" in report
    assert "execution_permission_granted: false" in report
    assert "stage_transition_allowed: false" in report
    assert "## Executive Summary" in report
    assert "## Risk Guard Status" in report
    assert "## Safety & Permission State" in report
    assert "order_endpoint_called: false" in report
    assert "secret_value_accessed: false" in report


def test_scan_report_contract_v2_marks_missing_optional_data_neutral(tmp_path):
    payload, report = _run_command(tmp_path, "--command", "scan", "--symbol", "BTC", "--dry-run", "--job-id", "job-scan-001")
    assert payload["symbol"] == "BTC"
    assert payload["review_only"] is True
    assert "symbol: BTC" in report
    assert "artifact_contract_version: agent_report_v2" in report
    assert "neutral_due_to_missing_optional_data" in report
    assert "## ResearchSignal Compatibility" in report
    assert "## Execution Guard" in report
    assert "No order intent is created" in report
