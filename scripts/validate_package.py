from __future__ import annotations

import json
import sys
from pathlib import Path

AGENT_ID = "crypto_ai_system"
FORBIDDEN_FILES = {".env", ".env.local", ".env.production", "secrets.json", "api_keys.json", "private_key.json"}
FORBIDDEN_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build", "large_raw_data", "cache"}


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _scan_forbidden(root: Path) -> list[str]:
    violations: list[str] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if rel == "release_artifacts" or rel.startswith("release_artifacts/"):
            continue
        name = path.name.lower()
        if path.is_dir() and name in FORBIDDEN_DIRS:
            violations.append(rel)
        if path.is_file() and name in FORBIDDEN_FILES:
            violations.append(rel)
    return violations


def _safe_defaults_valid(manifest: dict, defaults: dict) -> bool:
    required_false = ["live_trading_enabled", "order_execution_enabled", "auto_position_open_enabled", "withdrawal_enabled", "fund_transfer_enabled"]
    manifest_defaults = manifest.get("safe_defaults", {})
    return all(manifest_defaults.get(key) is False and defaults.get(key) is False for key in required_false)


def _cleanup_generated_forbidden_dirs(root: Path) -> None:
    for cache_dir in list(root.rglob("__pycache__")) + list(root.rglob(".pytest_cache")):
        if cache_dir.is_dir():
            for child in cache_dir.rglob("*"):
                if child.is_file():
                    child.unlink(missing_ok=True)
            for child in sorted([p for p in cache_dir.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
                child.rmdir()
            cache_dir.rmdir()


def main() -> int:
    root = _root_dir()
    _cleanup_generated_forbidden_dirs(root)
    checks: dict[str, str] = {}
    try:
        required_paths = [
            "agent_manifest.json",
            "agent_import_manifest.json",
            "README_AGENT.md",
            "scripts/run_command.py",
            "scripts/self_test.py",
            "scripts/validate_package.py",
            "scripts/docker_smoke.py",
            "scripts/build_agent_os_release.py",
            "scripts/validate_agent_os_import_package.py",
            "config/defaults.json",
            "config/command_map.json",
            "docs/AGENT_PACKAGE_BOUNDARY.md",
            "docs/AGENT_OS_IMPORT_COMPATIBILITY.md",
            "docs/RESEARCH_SIGNAL_V2_AGENT_CONTRACT.md",
            "docs/BACKTEST_FEEDBACK_AGENT_CONTRACT.md",
            "docs/PAPER_SIMULATION_AGENT_CONTRACT.md",
            "docs/ARTIFACT_REGISTRY_CONTRACT.md",
            "docs/SOURCE_HEALTH_AGENT_CONTRACT.md",
            "docs/LOCAL_PRICE_DATA_DRY_RUN_CONTRACT.md",
            "docs/PRICE_FEATURE_SNAPSHOT_CONTRACT.md",
            "examples/data/sample_price_schema.csv",
            "Dockerfile",
            "docker-compose.yml",
            ".dockerignore",
        ]
        for rel in required_paths:
            checks[rel] = "passed" if (root / rel).exists() else "failed"
        if any(value == "failed" for value in checks.values()):
            raise RuntimeError("Required Agent Package files are missing.")
        checks["dependencies"] = "passed" if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists() else "failed"
        if checks["dependencies"] != "passed":
            raise RuntimeError("requirements.txt or pyproject.toml is required.")
        manifest = _load_json(root / "agent_manifest.json")
        defaults = _load_json(root / "config/defaults.json")
        command_map = _load_json(root / "config/command_map.json")
        import_manifest = _load_json(root / "agent_import_manifest.json")
        checks["manifest_agent_id"] = "passed" if manifest.get("agent_id") == AGENT_ID else "failed"
        checks["manifest_entrypoint"] = "passed" if manifest.get("entrypoint") == "python scripts/run_command.py" else "failed"
        checks["manifest_self_test"] = "passed" if manifest.get("self_test") == "python scripts/self_test.py" else "failed"
        checks["commands"] = "passed" if {"daily", "scan", "signal", "source-health"}.issubset(manifest.get("commands", {})) and {"daily", "scan", "signal", "source-health"}.issubset(command_map) else "failed"
        checks["safe_defaults"] = "passed" if _safe_defaults_valid(manifest, defaults) else "failed"
        checks["live_disabled"] = "passed" if command_map.get("live", {}).get("enabled") is False else "failed"
        checks["package_boundary"] = "passed" if manifest.get("agent_package_contract", {}).get("boundary") == "crypto_ai_system_zip_only" and import_manifest.get("boundary") == "crypto_ai_system_zip_only" else "failed"
        checks["launcher_not_implemented_here"] = "passed" if manifest.get("agent_os_import", {}).get("launcher_import_manager_implemented_here") is False and manifest.get("agent_os_import", {}).get("telegram_router_implemented_here") is False else "failed"
        checks["no_execution_permission"] = "passed" if defaults.get("execution_permission_granted") is False and defaults.get("stage_transition_allowed") is False else "failed"
        checks["signal_contract"] = "passed" if defaults.get("signal_command_research_signal_v2_enabled") is True and defaults.get("signal_live_eligibility_must_be_false") is True and manifest.get("agent_package_contract", {}).get("signal_artifact_contract") == "research_signal_v2_agent_package_contract" else "failed"
        checks["backtest_feedback_contract"] = "passed" if defaults.get("backtest_command_contract_enabled") is True and defaults.get("feedback_command_contract_enabled") is True and manifest.get("agent_package_contract", {}).get("backtest_artifact_contract") == "backtest_review_v1" and manifest.get("agent_package_contract", {}).get("feedback_artifact_contract") == "feedback_review_v1" else "failed"
        checks["source_health_contract"] = "passed" if defaults.get("source_health_command_enabled") is True and defaults.get("source_health_artifact_contract") == "source_health_review_v1" and defaults.get("price_data_hard_required") is True and defaults.get("optional_data_missing_policy") == "neutral_due_to_missing" and manifest.get("agent_package_contract", {}).get("source_health_artifact_contract") == "source_health_review_v1" else "failed"
        checks["local_price_csv_contract"] = "passed" if defaults.get("local_price_csv_dry_run_enabled") is True and defaults.get("price_csv_schema_contract_version") == "price_csv_ohlcv_v1" and set(defaults.get("price_csv_required_columns", [])) >= {"timestamp", "symbol", "open", "high", "low", "close", "volume"} and defaults.get("price_data_connected_requires_real_local_csv") is True else "failed"
        checks["price_feature_snapshot_contract"] = "passed" if defaults.get("price_feature_snapshot_enabled") is True and defaults.get("price_feature_snapshot_contract_version") == "price_feature_snapshot_v1" and defaults.get("feature_snapshot_requires_valid_price_snapshot") is True and defaults.get("feature_snapshot_blocks_sample_stale_invalid_csv") is True and manifest.get("agent_package_contract", {}).get("price_feature_snapshot_contract") == "price_feature_snapshot_v1" else "failed"
        checks["paper_simulation_contract"] = "passed" if defaults.get("paper_command_contract_enabled") is True and defaults.get("paper_artifact_contract") == "paper_simulation_review_v1" and defaults.get("paper_command_requires_approval") is True and manifest.get("agent_package_contract", {}).get("paper_artifact_contract") == "paper_simulation_review_v1" and manifest.get("commands", {}).get("paper", {}).get("requires_approval") is True else "failed"
        checks["artifact_registry_contract"] = "passed" if defaults.get("artifact_registry_enabled") is True and defaults.get("stdout_json_artifact_hash_required") is True and manifest.get("agent_package_contract", {}).get("artifact_registry_contract") == "agent_artifact_registry_v1" and manifest.get("agent_package_contract", {}).get("artifact_metadata_sidecar_contract") == "agent_artifact_metadata_v1" else "failed"
        checks["launcher_simulation_defaults_removed"] = "passed" if "agent_os_import_manager_simulation_supported" not in defaults and "agent_os_simulated_inbox" not in defaults else "failed"
        docker = manifest.get("docker", {})
        dockerfile_text = (root / "Dockerfile").read_text(encoding="utf-8")
        compose_text = (root / "docker-compose.yml").read_text(encoding="utf-8")
        dockerignore_text = (root / ".dockerignore").read_text(encoding="utf-8")
        checks["docker_supported"] = "passed" if docker.get("supported") is True and manifest.get("compatibility", {}).get("runtime") == "docker_compatible_python" else "failed"
        checks["docker_entrypoint"] = "passed" if 'ENTRYPOINT ["python", "scripts/run_command.py"]' in dockerfile_text else "failed"
        checks["docker_self_test_service"] = "passed" if "crypto_ai_system_self_test" in compose_text and "scripts/self_test.py" in compose_text else "failed"
        checks["docker_secret_policy"] = "passed" if "env_file:" not in compose_text.lower() and "BINANCE_API_SECRET" not in compose_text and ".env" in dockerignore_text and "secrets.json" in dockerignore_text else "failed"
        checks["launcher_simulation_removed"] = "passed" if not (root / "scripts/simulate_agent_os_import_manager.py").exists() and not (root / "scripts/simulate_agent_os_local_launcher_import.py").exists() else "failed"
        forbidden = _scan_forbidden(root)
        checks["forbidden_files"] = "passed" if not forbidden else "failed"
        failed = [key for key, value in checks.items() if value != "passed"]
        if failed:
            raise RuntimeError(f"Package validation failed: {', '.join(failed)}; forbidden={forbidden}")
        print(json.dumps({"success": True, "status": "passed", "agent_id": AGENT_ID, "checks": checks, "error_message": None}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "status": "failed", "agent_id": AGENT_ID, "checks": checks, "error_message": str(exc)}, ensure_ascii=False))
        return 9


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
