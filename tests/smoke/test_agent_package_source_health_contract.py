import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def test_source_health_command_emits_review_only_contract(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_command.py",
            "--command",
            "source-health",
            "--dry-run",
            "--job-id",
            "job-source-health",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = _last_json(proc.stdout)
    assert payload["success"] is True
    assert payload["artifact_type"] == "source_health"
    assert payload["source_health_contract_version"] == "source_health_review_v1"
    assert payload["price_data_hard_required"] is True
    assert payload["price_data_connected"] is False
    assert payload["fresh_price_data_available"] is False
    assert payload["missing_optional_source_count"] == 4
    assert payload["optional_data_policy"] == "neutral_due_to_missing"
    assert payload["trading_candidate_allowed"] is False
    assert payload["paper_candidate_eligible"] is False
    assert payload["signed_testnet_candidate_eligible"] is False
    assert payload["live_candidate_eligible"] is False
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False

    artifact = Path(payload["artifact_path"])
    if not artifact.is_absolute():
        artifact = ROOT / artifact
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["artifact_contract_version"] == "source_health_review_v1"
    assert artifact_payload["source_gate"]["result"] == "blocked_review_only"
    assert artifact_payload["source_gate"]["fallback_sample_synthetic_source_blocks_candidates"] is True
    assert artifact_payload["optional_data_health"]["price"]["required"] is True
    assert artifact_payload["optional_data_health"]["price"]["trading_candidate_allowed"] is False
    assert artifact_payload["fallback_used"] is False
    assert artifact_payload["synthetic_used"] is False
    assert artifact_payload["sample_used"] is False
    assert artifact_payload["mock_used"] is False


def test_daily_scan_signal_expose_source_health_status(tmp_path):
    commands = [
        ["--command", "daily", "--dry-run"],
        ["--command", "scan", "--symbol", "BTC", "--dry-run"],
        ["--command", "signal", "--symbol", "BTC", "--dry-run"],
    ]
    for args in commands:
        proc = subprocess.run(
            [sys.executable, "scripts/run_command.py", *args, "--output-dir", str(tmp_path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout
        payload = _last_json(proc.stdout)
        assert payload["source_health_contract_version"] == "source_health_review_v1"
        assert payload["price_data_hard_required"] is True
        assert payload["fresh_price_data_available"] is False
        assert payload["optional_data_policy"] == "neutral_due_to_missing"
        assert payload["trading_candidate_allowed"] is False
        assert payload["execution_permission_granted"] is False
        assert payload["stage_transition_allowed"] is False
