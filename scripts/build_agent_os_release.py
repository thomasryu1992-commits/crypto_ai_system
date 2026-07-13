from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

AGENT_ID = "crypto_ai_system"
TOP_LEVEL = "crypto_ai_system"
KEY_CHECKSUM_FILES = [
    "agent_manifest.json",
    "agent_import_manifest.json",
    "README_AGENT.md",
    "requirements.txt",
    "pyproject.toml",
    "config/defaults.json",
    "config/command_map.json",
    "scripts/run_command.py",
    "scripts/self_test.py",
    "scripts/validate_package.py",
    "scripts/validate_agent_os_import_package.py",
    "scripts/build_agent_os_release.py",
    "scripts/docker_smoke.py",
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
FORBIDDEN_NAMES = {".env", ".env.local", ".env.production", "secrets.json", "api_keys.json", "private_key.json"}
FORBIDDEN_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build", "large_raw_data", "cache"}
EXCLUDED_PATH_PREFIXES = {"data/reports/", "release_artifacts/"}


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_forbidden_or_excluded(rel: str) -> bool:
    parts = Path(rel).parts
    lowered = [part.lower() for part in parts]
    if not parts:
        return True
    if lowered[-1] in FORBIDDEN_NAMES:
        return True
    if any(part in FORBIDDEN_DIRS for part in lowered[:-1]):
        return True
    if any(rel.startswith(prefix) for prefix in EXCLUDED_PATH_PREFIXES):
        return rel != "data/reports/.gitkeep"
    if rel.endswith(".pyc") or "/__pycache__/" in rel:
        return True
    return False


def build_import_manifest(root: Path) -> dict:
    manifest = _load_json(root / "agent_manifest.json")
    checksums: dict[str, str] = {}
    missing: list[str] = []
    for rel in KEY_CHECKSUM_FILES:
        path = root / rel
        if path.exists():
            checksums[rel] = _sha256_file(path)
        else:
            missing.append(rel)
    return {
        "schema_version": "1.0",
        "agent_id": AGENT_ID,
        "agent_name": manifest.get("agent_name", "Crypto AI System"),
        "version": manifest.get("version"),
        "package_type": "thomas_agent_os_agent_package",
        "boundary": "crypto_ai_system_zip_only",
        "expected_zip_top_level_dir": TOP_LEVEL,
        "entrypoint": manifest.get("entrypoint"),
        "self_test": manifest.get("self_test"),
        "validate_package": "python scripts/validate_package.py",
        "validate_import_package": "python scripts/validate_agent_os_import_package.py",
        "launcher_owned_responsibilities": [
            "agents_zip_inbox_scan",
            "0_IMPORT_ZIP.bat",
            "agents_installed_current_switch",
            "agent_registry_mutation",
            "telegram_bot_routing",
            "status_rendering",
            "duplicate_import_policy",
            "rollback_policy",
        ],
        "package_owned_responsibilities": [
            "manifest_metadata",
            "safe_defaults",
            "command_map",
            "standard_run_command_entrypoint",
            "self_test",
            "validate_package",
            "final_line_json_output",
            "docker_attach_files",
            "research_signal_v2_artifacts",
            "backtest_review_artifacts",
            "feedback_review_artifacts",
            "paper_simulation_review_artifacts",
            "source_health_review_artifacts",
            "local_price_csv_schema_validation",
            "price_data_snapshot_hashing",
            "price_feature_snapshot_generation",
            "data_snapshot_to_feature_snapshot_lineage",
            "artifact_sidecar_metadata",
            "artifact_index",
            "latest_artifact_pointers",
        ],
        "artifact_contracts": {
            "artifact_registry_contract": "agent_artifact_registry_v1",
            "artifact_metadata_sidecar_contract": "agent_artifact_metadata_v1",
            "artifact_index_contract": "agent_artifact_index_v1",
            "latest_pointer_contract": "agent_artifact_latest_pointer_v1",
            "stdout_json_artifact_hash_required": True,
            "paper_simulation_contract": "paper_simulation_review_v1",
            "source_health_contract": "source_health_review_v1",
            "local_price_csv_contract": "price_csv_ohlcv_v1",
            "price_feature_snapshot_contract": "price_feature_snapshot_v1",
        },
        "safe_defaults": {
            "live_trading_enabled": False,
            "order_execution_enabled": False,
            "auto_position_open_enabled": False,
            "withdrawal_enabled": False,
            "fund_transfer_enabled": False,
            "execution_permission_granted": False,
            "stage_transition_allowed": False,
        },
        "docker": manifest.get("docker", {}),
        "key_file_sha256": checksums,
        "missing_key_files": missing,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def write_import_manifest(root: Path) -> Path:
    path = root / "agent_import_manifest.json"
    path.write_text(json.dumps(build_import_manifest(root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _last_json(stdout: str) -> dict:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else {"success": False, "error_message": "No JSON returned"}


def _run(root: Path, args: list[str]) -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, *args], cwd=root, text=True, capture_output=True, env=env, timeout=120)
    payload = _last_json(proc.stdout)
    if proc.returncode != 0 or payload.get("success") is not True:
        raise RuntimeError(payload.get("error_message") or proc.stderr or f"Command failed: {args}")
    return payload


def build_release_zip(root: Path, output_dir: Path, zip_name: str | None = None) -> Path:
    manifest = _load_json(root / "agent_manifest.json")
    version = manifest.get("version") or "unknown"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / (zip_name or f"crypto_ai_system_v{version}.zip")
    if target.exists():
        target.unlink()
    files: list[tuple[Path, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _is_forbidden_or_excluded(rel):
            continue
        files.append((path, f"{TOP_LEVEL}/{rel}"))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path, arcname in sorted(files, key=lambda item: item[1]):
            zf.write(path, arcname)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Crypto AI System package-only Agent ZIP.")
    parser.add_argument("--output-dir", default="/mnt/data")
    parser.add_argument("--zip-name")
    parser.add_argument("--write-manifest-only", action="store_true")
    parser.add_argument("--skip-self-test", action="store_true")
    args = parser.parse_args(argv)
    root = _root_dir()
    try:
        import_manifest_path = write_import_manifest(root)
        validate_payload = _run(root, ["scripts/validate_package.py"])
        self_test_payload = None if args.skip_self_test else _run(root, ["scripts/self_test.py"])
        if args.write_manifest_only:
            payload = {
                "success": True,
                "status": "manifest_written",
                "agent_id": AGENT_ID,
                "boundary": "crypto_ai_system_zip_only",
                "import_manifest_path": import_manifest_path.as_posix(),
                "zip_path": None,
                "validate_package_passed": validate_payload.get("success") is True,
                "self_test_passed": None if self_test_payload is None else self_test_payload.get("success") is True,
                "execution_permission_granted": False,
                "stage_transition_allowed": False,
                "error_message": None,
            }
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        zip_path = build_release_zip(root, Path(args.output_dir), args.zip_name)
        import_validation = _run(root, ["scripts/validate_agent_os_import_package.py", "--zip-path", str(zip_path)])
        payload = {
            "success": True,
            "status": "release_built",
            "agent_id": AGENT_ID,
            "boundary": "crypto_ai_system_zip_only",
            "version": _load_json(root / "agent_manifest.json").get("version"),
            "import_manifest_path": import_manifest_path.as_posix(),
            "zip_path": str(zip_path),
            "zip_sha256": _sha256_file(zip_path),
            "validate_package_passed": validate_payload.get("success") is True,
            "self_test_passed": None if self_test_payload is None else self_test_payload.get("success") is True,
            "import_package_validation_passed": import_validation.get("success") is True,
            "expected_zip_top_level_dir": TOP_LEVEL,
            "execution_permission_granted": False,
            "stage_transition_allowed": False,
            "error_message": None,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "success": False,
            "status": "failed",
            "agent_id": AGENT_ID,
            "error_message": str(exc),
            "execution_permission_granted": False,
            "stage_transition_allowed": False,
        }, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
