from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

AGENT_ID = "crypto_ai_system"


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _last_json(stdout: str) -> dict:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("No stdout JSON returned.")
    return json.loads(lines[-1])


def _run_command(root: Path, *args: str) -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, "scripts/run_command.py", *args], cwd=root, text=True, capture_output=True, env=env, timeout=60)
    payload = _last_json(proc.stdout)
    if proc.returncode != 0 or payload.get("success") is not True:
        raise RuntimeError(payload.get("error_message") or proc.stderr or f"Command failed: {args}")
    return payload


def _safe_defaults_ok(defaults: dict, manifest: dict) -> bool:
    required_false = ["live_trading_enabled", "order_execution_enabled", "auto_position_open_enabled", "withdrawal_enabled", "fund_transfer_enabled"]
    safe_defaults = manifest.get("safe_defaults", {})
    return all(defaults.get(key) is False and safe_defaults.get(key) is False for key in required_false)


def _docker_files_ok(root: Path, manifest: dict) -> bool:
    docker = manifest.get("docker", {})
    required = ["Dockerfile", "docker-compose.yml", ".dockerignore", "scripts/docker_smoke.py"]
    if not docker.get("supported"):
        return False
    if any(not (root / rel).exists() for rel in required):
        return False
    dockerfile_text = (root / "Dockerfile").read_text(encoding="utf-8")
    compose_text = (root / "docker-compose.yml").read_text(encoding="utf-8")
    ignore_text = (root / ".dockerignore").read_text(encoding="utf-8")
    return 'ENTRYPOINT ["python", "scripts/run_command.py"]' in dockerfile_text and "crypto_ai_system_self_test" in compose_text and "scripts/self_test.py" in compose_text and ".env" in ignore_text and "secrets.json" in ignore_text


def _secrets_scan(root: Path) -> bool:
    forbidden_names = {".env", ".env.local", ".env.production", "secrets.json", "api_keys.json", "private_key.json"}
    return not any(path.is_file() and path.name.lower() in forbidden_names for path in root.rglob("*"))


def main() -> int:
    root = _root_dir()
    checks = {
        "manifest": "pending",
        "defaults": "pending",
        "command_map": "pending",
        "entrypoint": "pending",
        "dependencies": "pending",
        "package_import": "pending",
        "safe_defaults": "pending",
        "dry_run_daily": "pending",
        "dry_run_scan": "pending",
        "dry_run_signal": "pending",
        "dry_run_source_health": "pending",
        "dry_run_backtest": "pending",
        "dry_run_feedback": "pending",
        "dry_run_paper": "pending",
        "secrets_scan": "pending",
        "docker_files": "pending",
        "docker_smoke": "pending",
        "package_boundary": "pending",
        "launcher_not_implemented_here": "pending",
        "artifact_registry_stdout_contract": "pending",
        "release_manifest_write": "pending",
        "price_feature_snapshot_contract": "pending",
    }
    version = None
    try:
        manifest = _load_json(root / "agent_manifest.json")
        defaults = _load_json(root / "config/defaults.json")
        command_map = _load_json(root / "config/command_map.json")
        version = manifest.get("version")
        checks["manifest"] = "passed" if manifest.get("agent_id") == AGENT_ID else "failed"
        checks["defaults"] = "passed"
        checks["command_map"] = "passed" if {"daily", "scan"}.issubset(command_map) else "failed"
        checks["entrypoint"] = "passed" if (root / "scripts/run_command.py").exists() and manifest.get("entrypoint") == "python scripts/run_command.py" else "failed"
        checks["dependencies"] = "passed" if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists() else "failed"
        sys.path.insert(0, str(root / "src"))
        __import__("crypto_ai_system")
        checks["package_import"] = "passed"
        checks["safe_defaults"] = "passed" if _safe_defaults_ok(defaults, manifest) else "failed"
        daily_payload = _run_command(root, "--command", "daily", "--dry-run")
        checks["dry_run_daily"] = "passed"
        scan_payload = _run_command(root, "--command", "scan", "--symbol", "BTC", "--dry-run")
        checks["dry_run_scan"] = "passed"
        signal_payload = _run_command(root, "--command", "signal", "--symbol", "BTC", "--dry-run")
        checks["dry_run_signal"] = "passed" if signal_payload.get("artifact_type") == "signal" and signal_payload.get("live_eligibility") is False else "failed"
        source_health_payload = _run_command(root, "--command", "source-health", "--dry-run")
        checks["dry_run_source_health"] = "passed" if source_health_payload.get("artifact_type") == "source_health" and source_health_payload.get("source_health_contract_version") == "source_health_review_v1" and source_health_payload.get("trading_candidate_allowed") is False else "failed"
        checks["price_feature_snapshot_contract"] = "passed" if source_health_payload.get("feature_snapshot_contract_version") == "price_feature_snapshot_v1" and source_health_payload.get("feature_matrix_sha256") and source_health_payload.get("feature_snapshot_id") and source_health_payload.get("signed_testnet_candidate_eligible") is False else "failed"
        backtest_payload = _run_command(root, "--command", "backtest", "--dry-run")
        checks["dry_run_backtest"] = "passed" if backtest_payload.get("artifact_type") == "backtest" and backtest_payload.get("execution_permission_granted") is False else "failed"
        feedback_payload = _run_command(root, "--command", "feedback", "--dry-run")
        checks["dry_run_feedback"] = "passed" if feedback_payload.get("artifact_type") == "feedback" and feedback_payload.get("runtime_mutation_allowed") is False else "failed"
        paper_payload = _run_command(root, "--command", "paper", "--dry-run")
        checks["dry_run_paper"] = "passed" if paper_payload.get("artifact_type") == "paper_simulation" and paper_payload.get("paper_simulation_contract_version") == "paper_simulation_review_v1" and paper_payload.get("execution_permission_granted") is False else "failed"
        registry_payloads = [daily_payload, scan_payload, signal_payload, source_health_payload, backtest_payload, feedback_payload, paper_payload]
        checks["artifact_registry_stdout_contract"] = "passed" if all(
            payload.get("artifact_registry_updated") is True
            and isinstance(payload.get("artifact_sha256"), str) and len(payload.get("artifact_sha256", "")) == 64
            and payload.get("artifact_metadata_path")
            and payload.get("artifact_index_path")
            and payload.get("latest_pointer_path")
            and payload.get("execution_permission_granted") is False
            and payload.get("stage_transition_allowed") is False
            for payload in registry_payloads
        ) else "failed"
        checks["secrets_scan"] = "passed" if _secrets_scan(root) else "failed"
        checks["docker_files"] = "passed" if _docker_files_ok(root, manifest) else "failed"
        docker_proc = subprocess.run([sys.executable, "scripts/docker_smoke.py"], cwd=root, text=True, capture_output=True, env=os.environ.copy(), timeout=60)
        docker_payload = _last_json(docker_proc.stdout)
        if docker_proc.returncode != 0 or docker_payload.get("success") is not True:
            raise RuntimeError(docker_payload.get("error_message") or docker_proc.stderr or "Docker smoke validation failed.")
        checks["docker_smoke"] = "passed"
        checks["package_boundary"] = "passed" if manifest.get("agent_package_contract", {}).get("boundary") == "crypto_ai_system_zip_only" else "failed"
        checks["launcher_not_implemented_here"] = "passed" if manifest.get("agent_os_import", {}).get("launcher_import_manager_implemented_here") is False and manifest.get("agent_os_import", {}).get("telegram_router_implemented_here") is False else "failed"
        rel_proc = subprocess.run([sys.executable, "scripts/build_agent_os_release.py", "--write-manifest-only", "--skip-self-test"], cwd=root, text=True, capture_output=True, env=os.environ.copy(), timeout=60)
        rel_payload = _last_json(rel_proc.stdout)
        if rel_proc.returncode != 0 or rel_payload.get("success") is not True:
            raise RuntimeError(rel_payload.get("error_message") or rel_proc.stderr or "Release manifest write failed.")
        checks["release_manifest_write"] = "passed"
        failed = [key for key, value in checks.items() if value != "passed"]
        if failed:
            raise RuntimeError(f"Self-test failed checks: {failed}")
        print(json.dumps({"success": True, "status": "passed", "agent_id": AGENT_ID, "version": version, "checks": checks, "error_message": None}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "status": "failed", "agent_id": AGENT_ID, "version": version, "checks": checks, "error_message": str(exc)}, ensure_ascii=False))
        return 8


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
