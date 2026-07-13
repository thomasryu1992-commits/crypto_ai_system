from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

AGENT_ID = "crypto_ai_system"
EXPECTED_TOP_LEVEL = "crypto_ai_system"
REQUIRED_FILES = {
    "agent_manifest.json",
    "agent_import_manifest.json",
    "README_AGENT.md",
    "scripts/run_command.py",
    "scripts/self_test.py",
    "scripts/validate_package.py",
    "scripts/build_agent_os_release.py",
    "scripts/validate_agent_os_import_package.py",
    "scripts/docker_smoke.py",
    "docs/BACKTEST_FEEDBACK_AGENT_CONTRACT.md",
    "docs/PAPER_SIMULATION_AGENT_CONTRACT.md",
    "docs/ARTIFACT_REGISTRY_CONTRACT.md",
    "docs/SOURCE_HEALTH_AGENT_CONTRACT.md",
    "docs/LOCAL_PRICE_DATA_DRY_RUN_CONTRACT.md",
    "docs/PRICE_FEATURE_SNAPSHOT_CONTRACT.md",
    "examples/data/sample_price_schema.csv",
    "config/defaults.json",
    "config/command_map.json",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore",
}
FORBIDDEN_FILE_NAMES = {".env", ".env.local", ".env.production", "secrets.json", "api_keys.json", "private_key.json"}
FORBIDDEN_DIR_NAMES = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build", "large_raw_data", "cache"}
REQUIRED_FALSE_KEYS = [
    "live_trading_enabled",
    "order_execution_enabled",
    "auto_position_open_enabled",
    "withdrawal_enabled",
    "fund_transfer_enabled",
]


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _result(success: bool, status: str, checks: dict, error_message: str | None = None, **extra: object) -> dict:
    payload = {
        "success": success,
        "status": status,
        "agent_id": AGENT_ID,
        "checks": checks,
        "error_message": error_message,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
    }
    payload.update(extra)
    return payload


def _forbidden_parts(parts: tuple[str, ...]) -> list[str]:
    lowered = [part.lower() for part in parts]
    violations: list[str] = []
    if lowered and lowered[-1] in FORBIDDEN_FILE_NAMES:
        violations.append("/".join(parts))
    for part in lowered[:-1]:
        if part in FORBIDDEN_DIR_NAMES:
            violations.append("/".join(parts))
    return violations


def _validate_payloads(manifest: dict, defaults: dict, command_map: dict, import_manifest: dict) -> dict[str, str]:
    checks: dict[str, str] = {}
    checks["manifest_agent_id"] = "passed" if manifest.get("agent_id") == AGENT_ID else "failed"
    checks["manifest_entrypoint"] = "passed" if manifest.get("entrypoint") == "python scripts/run_command.py" else "failed"
    checks["manifest_self_test"] = "passed" if manifest.get("self_test") == "python scripts/self_test.py" else "failed"
    checks["package_contract_supported"] = "passed" if manifest.get("agent_package_contract", {}).get("supported") is True else "failed"
    checks["launcher_not_implemented_here"] = "passed" if manifest.get("agent_os_import", {}).get("launcher_import_manager_implemented_here") is False and manifest.get("agent_os_import", {}).get("telegram_router_implemented_here") is False else "failed"
    checks["import_manifest_agent_id"] = "passed" if import_manifest.get("agent_id") == AGENT_ID else "failed"
    checks["import_manifest_boundary"] = "passed" if import_manifest.get("boundary") == "crypto_ai_system_zip_only" else "failed"
    checks["import_manifest_top_level"] = "passed" if import_manifest.get("expected_zip_top_level_dir") == EXPECTED_TOP_LEVEL else "failed"
    checks["daily_scan_commands"] = "passed" if {"daily", "scan"}.issubset(command_map) else "failed"
    checks["source_health_command"] = "passed" if "source-health" in command_map and "source-health" in manifest.get("commands", {}) else "failed"
    checks["live_command_disabled"] = "passed" if command_map.get("live", {}).get("enabled") is False else "failed"
    safe_defaults = manifest.get("safe_defaults", {})
    checks["safe_defaults_false"] = "passed" if all(defaults.get(k) is False and safe_defaults.get(k) is False for k in REQUIRED_FALSE_KEYS) else "failed"
    checks["no_execution_permission"] = "passed" if defaults.get("execution_permission_granted") is False and defaults.get("stage_transition_allowed") is False else "failed"
    checks["docker_supported"] = "passed" if manifest.get("docker", {}).get("supported") is True else "failed"
    checks["backtest_feedback_contract"] = "passed" if defaults.get("backtest_command_contract_enabled") is True and defaults.get("feedback_command_contract_enabled") is True and manifest.get("agent_package_contract", {}).get("backtest_artifact_contract") == "backtest_review_v1" and manifest.get("agent_package_contract", {}).get("feedback_artifact_contract") == "feedback_review_v1" else "failed"
    checks["source_health_contract"] = "passed" if defaults.get("source_health_command_enabled") is True and defaults.get("source_health_artifact_contract") == "source_health_review_v1" and manifest.get("agent_package_contract", {}).get("source_health_artifact_contract") == "source_health_review_v1" else "failed"
    checks["local_price_csv_contract"] = "passed" if defaults.get("price_csv_schema_contract_version") == "price_csv_ohlcv_v1" and defaults.get("price_data_connected_requires_real_local_csv") is True else "failed"
    checks["price_feature_snapshot_contract"] = "passed" if defaults.get("price_feature_snapshot_enabled") is True and defaults.get("price_feature_snapshot_contract_version") == "price_feature_snapshot_v1" and manifest.get("agent_package_contract", {}).get("price_feature_snapshot_contract") == "price_feature_snapshot_v1" else "failed"
    checks["paper_simulation_contract"] = "passed" if defaults.get("paper_command_contract_enabled") is True and defaults.get("paper_artifact_contract") == "paper_simulation_review_v1" and manifest.get("agent_package_contract", {}).get("paper_artifact_contract") == "paper_simulation_review_v1" and command_map.get("paper", {}).get("requires_approval") is True else "failed"
    checks["artifact_registry_contract"] = "passed" if defaults.get("artifact_registry_enabled") is True and defaults.get("stdout_json_artifact_hash_required") is True and manifest.get("agent_package_contract", {}).get("artifact_registry_contract") == "agent_artifact_registry_v1" else "failed"
    return checks


def validate_directory(root: Path) -> dict:
    checks: dict[str, str] = {}
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).exists()]
    checks["required_files"] = "passed" if not missing else "failed"
    forbidden: list[str] = []
    for path in root.rglob("*"):
        forbidden.extend(_forbidden_parts(path.relative_to(root).parts))
    checks["forbidden_paths"] = "passed" if not forbidden else "failed"
    manifest = _load_json(root / "agent_manifest.json") if (root / "agent_manifest.json").exists() else {}
    defaults = _load_json(root / "config/defaults.json") if (root / "config/defaults.json").exists() else {}
    command_map = _load_json(root / "config/command_map.json") if (root / "config/command_map.json").exists() else {}
    import_manifest = _load_json(root / "agent_import_manifest.json") if (root / "agent_import_manifest.json").exists() else {}
    checks.update(_validate_payloads(manifest, defaults, command_map, import_manifest))
    failed = [key for key, value in checks.items() if value != "passed"]
    return _result(not failed, "passed" if not failed else "failed", checks, None if not failed else f"Directory validation failed: {failed}; missing={missing}; forbidden={forbidden[:10]}", package_type="directory", expected_zip_top_level_dir=EXPECTED_TOP_LEVEL)


def _zip_read_json(zf: zipfile.ZipFile, member: str) -> dict:
    with zf.open(member) as handle:
        return json.loads(handle.read().decode("utf-8"))


def validate_zip(zip_path: Path) -> dict:
    checks: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        names = [name for name in zf.namelist() if name and not name.endswith("/")]
        top_levels = sorted({name.split("/", 1)[0] for name in names})
        checks["single_top_level_dir"] = "passed" if top_levels == [EXPECTED_TOP_LEVEL] else "failed"
        required_members = {f"{EXPECTED_TOP_LEVEL}/{rel}" for rel in REQUIRED_FILES}
        name_set = set(names)
        missing = sorted(required_members - name_set)
        checks["required_files"] = "passed" if not missing else "failed"
        forbidden: list[str] = []
        for name in names:
            forbidden.extend(_forbidden_parts(tuple(name.split("/"))[1:]))
        checks["forbidden_paths"] = "passed" if not forbidden else "failed"
        prefix = f"{EXPECTED_TOP_LEVEL}/"
        manifest = _zip_read_json(zf, prefix + "agent_manifest.json") if prefix + "agent_manifest.json" in name_set else {}
        defaults = _zip_read_json(zf, prefix + "config/defaults.json") if prefix + "config/defaults.json" in name_set else {}
        command_map = _zip_read_json(zf, prefix + "config/command_map.json") if prefix + "config/command_map.json" in name_set else {}
        import_manifest = _zip_read_json(zf, prefix + "agent_import_manifest.json") if prefix + "agent_import_manifest.json" in name_set else {}
        checks.update(_validate_payloads(manifest, defaults, command_map, import_manifest))
    failed = [key for key, value in checks.items() if value != "passed"]
    return _result(not failed, "passed" if not failed else "failed", checks, None if not failed else f"ZIP validation failed: {failed}; top_levels={top_levels}; missing={missing[:10]}; forbidden={forbidden[:10]}", package_type="zip", zip_path=str(zip_path), expected_zip_top_level_dir=EXPECTED_TOP_LEVEL)


def _cleanup_generated_forbidden_dirs(root: Path) -> None:
    for cache_dir in list(root.rglob("__pycache__")) + list(root.rglob(".pytest_cache")):
        if cache_dir.is_dir():
            for child in cache_dir.rglob("*"):
                if child.is_file():
                    child.unlink(missing_ok=True)
            for child in sorted([p for p in cache_dir.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
                child.rmdir()
            cache_dir.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Crypto AI System package-only Agent ZIP shape.")
    parser.add_argument("--zip-path")
    parser.add_argument("--package-root")
    args = parser.parse_args(argv)
    try:
        if not args.zip_path:
            _cleanup_generated_forbidden_dirs(Path(args.package_root).resolve() if args.package_root else _root_dir())
        payload = validate_zip(Path(args.zip_path).resolve()) if args.zip_path else validate_directory(Path(args.package_root).resolve() if args.package_root else _root_dir())
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get("success") is True else 9
    except Exception as exc:
        print(json.dumps(_result(False, "failed", {}, str(exc)), ensure_ascii=False))
        return 9


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
