import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def test_daily_dry_run_outputs_json_and_artifact():
    proc = subprocess.run(
        [sys.executable, "scripts/run_command.py", "--command", "daily", "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    payload = _last_json(proc.stdout)
    assert proc.returncode == 0
    assert payload["success"] is True
    assert payload["status"] == "completed"
    assert payload["agent_id"] == "crypto_ai_system"
    assert payload["command"] == "daily"
    assert payload["artifact_path"]
    assert (ROOT / payload["artifact_path"]).exists()
