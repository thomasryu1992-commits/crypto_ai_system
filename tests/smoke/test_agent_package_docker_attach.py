import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _last_json(stdout: str) -> dict:
    return json.loads([line for line in stdout.splitlines() if line.strip()][-1])


def test_docker_attach_files_exist_and_are_manifested():
    manifest = json.loads((ROOT / "agent_manifest.json").read_text(encoding="utf-8"))
    assert manifest["docker"]["supported"] is True
    assert manifest["docker"]["dockerfile"] == "Dockerfile"
    assert manifest["docker"]["compose_file"] == "docker-compose.yml"
    assert manifest["docker"]["entrypoint"] == "python scripts/run_command.py"
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / ".dockerignore").exists()
    assert (ROOT / "scripts" / "docker_smoke.py").exists()


def test_dockerfile_preserves_standard_run_command_entrypoint():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["python", "scripts/run_command.py"]' in text
    assert 'CMD ["--command", "daily", "--dry-run"]' in text
    assert "CRYPTO_AI_SYSTEM_CONTAINER_MODE" in text
    assert "local_launcher" in text


def test_compose_has_self_test_service_and_no_secret_env_file():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "crypto_ai_system_self_test" in text
    assert "scripts/self_test.py" in text
    assert "env_file:" not in text.lower()
    assert "BINANCE_API_SECRET" not in text
    assert "API_SECRET" not in text


def test_dockerignore_excludes_secret_and_cache_files():
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for token in [".env", ".env.*", "secrets.json", "api_keys.json", "private_key.json", "__pycache__", ".git"]:
        assert token in text


def test_docker_smoke_script_returns_final_json():
    proc = subprocess.run(
        [sys.executable, "scripts/docker_smoke.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    payload = _last_json(proc.stdout)
    assert proc.returncode == 0
    assert payload["success"] is True
    assert payload["status"] == "passed"
    assert payload["execution_permission_granted"] is False
    assert payload["stage_transition_allowed"] is False
