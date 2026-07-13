import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_command(tmp_path: Path, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "scripts/run_command.py", *args, "--output-dir", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return _last_json(proc.stdout)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def test_daily_command_writes_sidecar_index_and_latest_pointer(tmp_path):
    payload = _run_command(tmp_path, "--command", "daily", "--dry-run", "--job-id", "job-artifact-daily")
    artifact = _resolve(payload["artifact_path"])
    sidecar = _resolve(payload["artifact_metadata_path"])
    index = _resolve(payload["artifact_index_path"])
    latest = _resolve(payload["latest_pointer_path"])

    assert artifact.exists()
    assert sidecar.exists()
    assert index.exists()
    assert latest.exists()
    assert payload["artifact_registry_updated"] is True
    assert payload["artifact_sha256"] == _sha256(artifact)
    assert payload["artifact_metadata_sha256"] == _sha256(sidecar)
    assert len(payload["artifact_id"]) == 24
    assert len(payload["artifact_sha256"]) == 64

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["sidecar_contract_version"] == "agent_artifact_metadata_v1"
    assert sidecar_payload["artifact_registry_contract_version"] == "agent_artifact_registry_v1"
    assert sidecar_payload["artifact_id"] == payload["artifact_id"]
    assert sidecar_payload["execution_permission_granted"] is False
    assert sidecar_payload["stage_transition_allowed"] is False
    assert sidecar_payload["order_endpoint_called"] is False
    assert sidecar_payload["secret_value_accessed"] is False

    index_payload = json.loads(index.read_text(encoding="utf-8"))
    assert index_payload["artifact_index_contract_version"] == "agent_artifact_index_v1"
    assert index_payload["artifact_count"] >= 1
    assert any(item["artifact_id"] == payload["artifact_id"] for item in index_payload["artifacts"])

    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    assert latest_payload["latest_pointer_contract_version"] == "agent_artifact_latest_pointer_v1"
    assert latest_payload["artifact_id"] == payload["artifact_id"]
    assert latest_payload["command"] == "daily"


def test_all_core_commands_emit_artifact_registry_stdout_fields(tmp_path):
    commands = [
        ["--command", "daily", "--dry-run", "--job-id", "job-reg-daily"],
        ["--command", "scan", "--symbol", "BTC", "--dry-run", "--job-id", "job-reg-scan"],
        ["--command", "signal", "--symbol", "BTC", "--dry-run", "--job-id", "job-reg-signal"],
        ["--command", "source-health", "--dry-run", "--job-id", "job-reg-source-health"],
        ["--command", "backtest", "--dry-run", "--job-id", "job-reg-backtest"],
        ["--command", "feedback", "--dry-run", "--job-id", "job-reg-feedback"],
        ["--command", "paper", "--dry-run", "--job-id", "job-reg-paper"],
    ]
    payloads = [_run_command(tmp_path, *args) for args in commands]
    for payload in payloads:
        assert payload["success"] is True
        assert payload["artifact_registry_updated"] is True
        assert len(payload["artifact_id"]) == 24
        assert len(payload["artifact_sha256"]) == 64
        assert Path(payload["artifact_metadata_path"]).exists()
        assert Path(payload["artifact_index_path"]).exists()
        assert Path(payload["latest_pointer_path"]).exists()
        assert payload["execution_permission_granted"] is False
        assert payload["stage_transition_allowed"] is False

    index_payload = json.loads((tmp_path / "artifact_index.json").read_text(encoding="utf-8"))
    commands_seen = {item["command"] for item in index_payload["artifacts"]}
    assert {"daily", "scan", "signal", "source-health", "backtest", "feedback", "paper"}.issubset(commands_seen)
    for command in commands_seen:
        if command in {"daily", "scan", "signal", "source-health", "backtest", "feedback", "paper"}:
            assert (tmp_path / "latest" / f"latest_{command}.json").exists()
