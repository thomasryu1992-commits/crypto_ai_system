import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def test_safe_defaults_disable_live_execution():
    manifest = _load_json(ROOT / "agent_manifest.json")
    defaults = _load_json(ROOT / "config" / "defaults.json")
    for key in [
        "live_trading_enabled",
        "order_execution_enabled",
        "auto_position_open_enabled",
        "withdrawal_enabled",
        "fund_transfer_enabled",
    ]:
        assert manifest["safe_defaults"][key] is False
        assert defaults[key] is False
    assert "live_trading" in manifest["disabled_capabilities"]


def test_live_command_is_blocked_and_returns_json():
    proc = subprocess.run(
        [sys.executable, "scripts/run_command.py", "--command", "live", "--symbol", "BTC"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    payload = _last_json(proc.stdout)
    assert proc.returncode != 0
    assert payload["success"] is False
    assert payload["status"] == "blocked"
    assert payload["agent_id"] == "crypto_ai_system"
