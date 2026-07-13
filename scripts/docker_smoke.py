from __future__ import annotations

import json
import sys
from pathlib import Path

AGENT_ID = "crypto_ai_system"


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _result(success: bool, status: str, checks: dict[str, str], error_message: str | None = None) -> dict:
    return {
        "success": success,
        "status": status,
        "agent_id": AGENT_ID,
        "checks": checks,
        "error_message": error_message,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
    }


def _contains_forbidden_secret_reference(text: str) -> bool:
    lowered = text.lower()
    forbidden_fragments = [
        "env_file:",
        "binance_api_secret",
        "api_secret",
        "private_key",
        "secrets.json",
        "api_keys.json",
    ]
    return any(fragment in lowered for fragment in forbidden_fragments)


def main() -> int:
    root = _root_dir()
    checks = {
        "dockerfile": "pending",
        "compose": "pending",
        "dockerignore": "pending",
        "entrypoint": "pending",
        "self_test_service": "pending",
        "secret_policy": "pending",
        "safe_runtime_mode": "pending",
    }
    try:
        dockerfile = root / "Dockerfile"
        compose = root / "docker-compose.yml"
        dockerignore = root / ".dockerignore"
        checks["dockerfile"] = "passed" if dockerfile.exists() else "failed"
        checks["compose"] = "passed" if compose.exists() else "failed"
        checks["dockerignore"] = "passed" if dockerignore.exists() else "failed"
        if any(checks[key] == "failed" for key in ("dockerfile", "compose", "dockerignore")):
            raise RuntimeError("Docker attach files are missing.")

        docker_text = dockerfile.read_text(encoding="utf-8")
        compose_text = compose.read_text(encoding="utf-8")
        ignore_text = dockerignore.read_text(encoding="utf-8")

        checks["entrypoint"] = "passed" if 'ENTRYPOINT ["python", "scripts/run_command.py"]' in docker_text else "failed"
        checks["self_test_service"] = "passed" if 'crypto_ai_system_self_test' in compose_text and 'scripts/self_test.py' in compose_text else "failed"
        checks["secret_policy"] = "passed" if not _contains_forbidden_secret_reference(compose_text) and ".env" in ignore_text and "secrets.json" in ignore_text else "failed"
        checks["safe_runtime_mode"] = "passed" if "CRYPTO_AI_SYSTEM_CONTAINER_MODE" in docker_text and "local_launcher" in docker_text and "local_launcher" in compose_text else "failed"

        failed = [key for key, value in checks.items() if value != "passed"]
        if failed:
            raise RuntimeError(f"Docker smoke validation failed: {', '.join(failed)}")
        print(json.dumps(_result(True, "passed", checks), ensure_ascii=False))
        return 0
    except Exception as exc:
        for key, value in list(checks.items()):
            if value == "pending":
                checks[key] = "skipped"
        print(json.dumps(_result(False, "failed", checks, str(exc)), ensure_ascii=False))
        return 9


if __name__ == "__main__":
    raise SystemExit(main())
