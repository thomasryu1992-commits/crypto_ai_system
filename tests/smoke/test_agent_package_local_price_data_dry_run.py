import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def _write_config(tmp_path: Path, price_dir: Path) -> Path:
    defaults = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
    defaults["local_price_data_dir"] = str(price_dir)
    defaults["local_price_data_max_age_hours"] = 72
    config_path = tmp_path / "defaults.local.json"
    config_path.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


def _run(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "scripts/run_command.py", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return _last_json(proc.stdout)


def test_source_health_accepts_fresh_real_local_price_csv_for_review_only_reporting(tmp_path):
    price_dir = tmp_path / "price_data"
    price_dir.mkdir()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    price_file = price_dir / "btc_1h_ohlcv.csv"
    price_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        f"{now},BTC,100000,101000,99000,100500,123.45\n",
        encoding="utf-8",
    )
    config_path = _write_config(tmp_path, price_dir)
    payload = _run(
        "--command",
        "source-health",
        "--dry-run",
        "--config",
        str(config_path),
        "--output-dir",
        str(tmp_path / "reports"),
    )
    assert payload["success"] is True
    assert payload["price_data_connected"] is True
    assert payload["fresh_price_data_available"] is True
    assert payload["local_csv_detected"] is True
    assert payload["price_csv_schema_valid"] is True
    assert payload["selected_price_csv_sha256"] and len(payload["selected_price_csv_sha256"]) == 64
    assert payload["data_snapshot_id"]
    assert payload["data_snapshot_manifest_sha256"] and len(payload["data_snapshot_manifest_sha256"]) == 64
    assert payload["trading_candidate_allowed"] is False
    assert payload["signed_testnet_candidate_eligible"] is False
    assert payload["live_candidate_eligible"] is False
    artifact = Path(payload["artifact_path"])
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["source_gate"]["result"] == "review_only_valid_price_data"
    assert artifact_payload["source_gate"]["trading_candidate_allowed"] is False
    assert artifact_payload["optional_data_health"]["price"]["price_data_connected"] is True


def test_sample_price_csv_is_detected_but_never_connected_or_candidate_eligible(tmp_path):
    config_path = _write_config(tmp_path, ROOT / "examples" / "data")
    payload = _run(
        "--command",
        "source-health",
        "--dry-run",
        "--config",
        str(config_path),
        "--output-dir",
        str(tmp_path / "reports"),
    )
    assert payload["local_csv_detected"] is True
    assert payload["price_csv_schema_valid"] is True
    assert payload["price_data_connected"] is False
    assert payload["fresh_price_data_available"] is False
    assert payload["trading_candidate_allowed"] is False
    artifact = Path(payload["artifact_path"])
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["sample_flag"] is True
    assert artifact_payload["sample_used"] is True
    assert artifact_payload["source_gate"]["result"] == "blocked_review_only"
    assert artifact_payload["source_gate"]["reason"] == "SAMPLE_PRICE_CSV_BLOCKS_CANDIDATE_ELIGIBILITY"
    assert artifact_payload["signed_testnet_candidate_eligible"] is False
    assert artifact_payload["live_candidate_eligible"] is False


def test_signal_references_fresh_local_price_csv_but_keeps_execution_disabled(tmp_path):
    price_dir = tmp_path / "price_data"
    price_dir.mkdir()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    (price_dir / "btc_1h_ohlcv.csv").write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        f"{now},BTC,100000,101000,99000,100500,123.45\n",
        encoding="utf-8",
    )
    config_path = _write_config(tmp_path, price_dir)
    payload = _run(
        "--command",
        "signal",
        "--symbol",
        "BTC",
        "--dry-run",
        "--config",
        str(config_path),
        "--output-dir",
        str(tmp_path / "reports"),
    )
    assert payload["price_data_connected"] is True
    assert payload["fresh_price_data_available"] is True
    assert payload["data_snapshot_id"]
    assert payload["live_eligibility"] is False
    assert payload["live_candidate_eligible"] is False
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
