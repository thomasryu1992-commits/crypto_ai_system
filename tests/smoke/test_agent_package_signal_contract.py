import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def _run_signal(tmp_path: Path, symbol: str = "BTC") -> tuple[dict, dict]:
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_command.py",
            "--command",
            "signal",
            "--symbol",
            symbol,
            "--dry-run",
            "--job-id",
            "job-signal-001",
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
    artifact = Path(payload["artifact_path"])
    if not artifact.is_absolute():
        artifact = ROOT / artifact
    assert artifact.exists()
    return payload, json.loads(artifact.read_text(encoding="utf-8"))


def test_signal_command_emits_research_signal_v2_contract(tmp_path):
    payload, signal = _run_signal(tmp_path)
    assert payload["success"] is True
    assert payload["artifact_type"] == "signal"
    assert payload["artifact_format"] == "json"
    assert payload["review_only"] is True
    assert payload["live_eligibility"] is False
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
    assert payload["research_signal_id"] == signal["research_signal_id"]
    assert payload["signal_version"] == signal["signal_version"]

    required = [
        "research_signal_id",
        "signal_version",
        "profile_id",
        "profile_version",
        "config_version",
        "data_snapshot_id",
        "feature_snapshot_id",
        "feature_matrix_sha256",
        "source_bundle_sha256",
        "data_snapshot_manifest_sha256",
        "optional_data_health",
        "missing_optional_source_count",
        "stale_optional_source_count",
        "created_at_utc",
    ]
    for field in required:
        assert signal.get(field) not in (None, ""), field

    assert signal["schema_version"] == "2.0"
    assert signal["artifact_contract_version"] == "research_signal_v2_agent_package_contract"
    assert signal["symbol"] == "BTC"
    assert signal["timeframe"] == "1h"
    assert len(signal["feature_matrix_sha256"]) == 64
    assert len(signal["source_bundle_sha256"]) == 64


def test_signal_contract_blocks_live_and_marks_missing_optional_neutral(tmp_path):
    _, signal = _run_signal(tmp_path, "ETH")
    assert signal["symbol"] == "ETH"
    assert signal["neutral_due_to_missing"] is True
    assert signal["missing_optional_data_neutral"] is True
    assert signal["missing_optional_source_count"] >= 4
    assert signal["stale_optional_source_count"] == 0
    assert signal["live_eligibility"] is False
    assert signal["live_candidate_eligible"] is False
    assert signal["signed_testnet_candidate_eligible"] is False
    assert signal["paper_candidate_eligible"] is False
    assert signal["trade_permission"]["blocked"] is True
    assert signal["trade_permission"]["execution_permission_granted"] is False
    assert signal["trade_permission"]["stage_transition_allowed"] is False
    assert signal["entry_allowed"] is False
    assert signal["entry_side"] == "FLAT"
    assert signal["fallback_flag"] is False
    assert signal["synthetic_flag"] is False
    assert signal["sample_flag"] is False
    assert signal["legacy_fallback_used"] is False
    assert signal["order_endpoint_called"] is False
    assert signal["secret_value_accessed"] is False
