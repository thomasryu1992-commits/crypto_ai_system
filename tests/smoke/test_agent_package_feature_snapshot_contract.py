import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


def _run(tmp_path: Path, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "scripts/run_command.py", *args, "--output-dir", str(tmp_path / "reports")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return _last_json(proc.stdout)


def _fresh_price_dir(tmp_path: Path) -> Path:
    price_dir = tmp_path / "price_data"
    price_dir.mkdir()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    prev = now - timedelta(hours=1)
    (price_dir / "btc_1h_ohlcv.csv").write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        f"{prev.isoformat().replace('+00:00', 'Z')},BTC,99000,100000,98000,99500,100.0\n"
        f"{now.isoformat().replace('+00:00', 'Z')},BTC,99500,101000,99000,100500,123.45\n",
        encoding="utf-8",
    )
    return price_dir


def test_source_health_builds_feature_snapshot_from_fresh_real_local_csv(tmp_path):
    config_path = _write_config(tmp_path, _fresh_price_dir(tmp_path))
    payload = _run(tmp_path, "--command", "source-health", "--dry-run", "--config", str(config_path))

    assert payload["success"] is True
    assert payload["price_data_connected"] is True
    assert payload["feature_snapshot_contract_version"] == "price_feature_snapshot_v1"
    assert payload["feature_snapshot_created"] is True
    assert payload["feature_snapshot_status"] == "created_review_only"
    assert payload["feature_snapshot_id"]
    assert len(payload["feature_matrix_sha256"]) == 64
    assert payload["feature_source_data_snapshot_id"] == payload["data_snapshot_id"]
    assert payload["signed_testnet_candidate_eligible"] is False
    assert payload["live_candidate_eligible"] is False

    artifact = Path(payload["artifact_path"])
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    feature_snapshot = artifact_payload["feature_snapshot"]
    assert feature_snapshot["feature_snapshot_created"] is True
    assert feature_snapshot["feature_snapshot_blocked_by_sample_stale_invalid"] is False
    assert feature_snapshot["feature_matrix"]["features"]["latest_close"] == 100500.0
    assert feature_snapshot["feature_matrix"]["features"]["row_count"] == 2
    assert feature_snapshot["trading_candidate_allowed"] is False


def test_signal_reuses_price_feature_snapshot_lineage_without_enabling_execution(tmp_path):
    config_path = _write_config(tmp_path, _fresh_price_dir(tmp_path))
    source_payload = _run(tmp_path, "--command", "source-health", "--dry-run", "--config", str(config_path))
    signal_payload = _run(tmp_path, "--command", "signal", "--symbol", "BTC", "--dry-run", "--config", str(config_path))

    assert signal_payload["feature_snapshot_contract_version"] == "price_feature_snapshot_v1"
    assert signal_payload["feature_snapshot_created"] is True
    assert signal_payload["feature_snapshot_id"] == source_payload["feature_snapshot_id"]
    assert signal_payload["feature_matrix_sha256"] == source_payload["feature_matrix_sha256"]
    assert signal_payload["data_snapshot_id"] == source_payload["data_snapshot_id"]
    assert signal_payload["execution_permission_granted"] is False
    assert signal_payload["stage_transition_allowed"] is False

    artifact = Path(signal_payload["artifact_path"])
    signal = json.loads(artifact.read_text(encoding="utf-8"))
    assert signal["feature_snapshot_created"] is True
    assert signal["feature_snapshot_id"] == source_payload["feature_snapshot_id"]
    assert signal["features"]["features"]["latest_close"] == 100500.0
    assert signal["trade_permission"]["blocked"] is True
    assert signal["signed_testnet_candidate_eligible"] is False
    assert signal["live_candidate_eligible"] is False


def test_sample_price_csv_blocks_feature_snapshot_creation(tmp_path):
    config_path = _write_config(tmp_path, ROOT / "examples" / "data")
    payload = _run(tmp_path, "--command", "source-health", "--dry-run", "--config", str(config_path))

    assert payload["local_csv_detected"] is True
    assert payload["price_csv_schema_valid"] is True
    assert payload["price_data_connected"] is False
    assert payload["feature_snapshot_contract_version"] == "price_feature_snapshot_v1"
    assert payload["feature_snapshot_created"] is False
    assert payload["feature_snapshot_status"] == "blocked_review_only"
    assert "SAMPLE_PRICE_CSV_BLOCKS_FEATURE_SNAPSHOT" in payload["feature_snapshot_status_reason"]
    assert payload["feature_snapshot_id"]
    assert payload["signed_testnet_candidate_eligible"] is False
    assert payload["live_candidate_eligible"] is False
