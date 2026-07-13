from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Iterable

DEFAULT_DIST = "dist/p45_package_splits"

SOURCE_INCLUDE_PREFIXES = {
    ".github",
    "agent_contracts",
    "agents",
    "config",
    "docs",
    "scripts",
    "src",
    "tests",
    "external_runtime_packages",
}
SOURCE_INCLUDE_NAMES = {
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "pyproject.toml",
    "README.md",
    "CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md",
    "requirements.txt",
}

VALIDATION_INCLUDE_PREFIXES = {
    "storage/latest",
    "storage/logs",
    "docs",
}
VALIDATION_REGISTRY_NAMES = {
    "agent_eval_registry.jsonl",
    "agent_contract_registry.jsonl",
    "agent_library_contract_review_registry.jsonl",
    "p30_final_activation_readiness_go_no_go_matrix_registry.jsonl",
    "p43_operator_evidence_archive_round_trip_seal_registry.jsonl",
    "p44_external_review_packet_intake_validator_registry.jsonl",
    "p45_external_review_packet_round_trip_closure_registry.jsonl",
    "p53_operator_controlled_p7_import_action_boundary_registry.jsonl",
    "p54_separate_p7_import_executor_final_guard_registry.jsonl",
    "p55_disabled_p7_importer_atomic_append_transaction_registry.jsonl",
    "p56_transactional_evidence_store_registry.jsonl",
    "p57_transactional_p7_importer_integration_registry.jsonl",
    "p58_external_runtime_signed_testnet_evidence_acquisition_registry.jsonl",
    "p59_separate_testnet_external_adapter_package_registry.jsonl",
    "p60_external_signer_http_transport_injection_harness_registry.jsonl",
    "p61_real_testnet_order_test_dry_validation_adapter_registry.jsonl",
    "p62_operator_side_external_order_test_execution_kit_registry.jsonl",
    "p66_operator_activation_intake_for_real_order_test_registry.jsonl",
    "p67_real_order_test_redacted_evidence_receipt_registry.jsonl",
    "p68_real_order_test_operator_run_package_registry.jsonl",
}

RUNTIME_INCLUDE_PREFIXES = {
    "src",
    "config",
    "scripts",
    "docs",
    "agents",
    "agent_contracts",
}
RUNTIME_INCLUDE_NAMES = {
    ".env.example",
    "pyproject.toml",
    "README.md",
    "CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md",
}
RUNTIME_EXCLUDED_SCRIPT_PREFIXES = {
    "scripts/build_p",
    "scripts/run_p",
}

EXCLUDED_DIR_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".zip"}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_clean_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    rel_posix = rel.as_posix()
    if path.is_dir():
        return False
    if set(rel.parts) & EXCLUDED_DIR_PARTS:
        return False
    if any(rel_posix.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return False
    return True


def include_source(path: Path, root: Path) -> bool:
    if not _is_clean_file(path, root):
        return False
    rel = _rel(path, root)
    if rel in SOURCE_INCLUDE_NAMES:
        return True
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in SOURCE_INCLUDE_PREFIXES)


def include_validation(path: Path, root: Path) -> bool:
    if not _is_clean_file(path, root):
        return False
    rel = _rel(path, root)
    if any(rel == prefix or rel.startswith(prefix + "/") for prefix in VALIDATION_INCLUDE_PREFIXES):
        return True
    if rel.startswith("storage/registries/") and Path(rel).name in VALIDATION_REGISTRY_NAMES:
        return True
    return False


def include_full_audit(path: Path, root: Path) -> bool:
    if not _is_clean_file(path, root):
        return False
    rel = _rel(path, root)
    return (
        rel.startswith("storage/")
        or rel.startswith("data/reports/")
        or rel.startswith("data/stores/")
        or rel.startswith("docs/")
        or rel in {"README.md", "CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md"}
    )


def include_runtime(path: Path, root: Path) -> bool:
    if not _is_clean_file(path, root):
        return False
    rel = _rel(path, root)
    if rel.startswith("storage/") or rel.startswith("data/reports/") or rel.startswith("data/stores/"):
        return False
    if rel in RUNTIME_INCLUDE_NAMES:
        return True
    if rel.startswith("scripts/") and any(rel.startswith(prefix) for prefix in RUNTIME_EXCLUDED_SCRIPT_PREFIXES):
        # Keep runtime package small: review packet generators stay in source/evidence packages.
        return False
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in RUNTIME_INCLUDE_PREFIXES)



def include_external_adapter_package(path: Path, root: Path) -> bool:
    if not _is_clean_file(path, root):
        return False
    rel = _rel(path, root)
    return (
        rel in {"external_runtime_packages/__init__.py", "external_runtime_packages/pyproject.toml"}
        or rel == "external_runtime_packages/binance_futures_testnet_adapter"
        or rel.startswith("external_runtime_packages/binance_futures_testnet_adapter/")
    )


def build_zip(root: Path, output: Path, include_fn, package_root: str) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    count = 0
    size = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if include_fn(path, root):
                rel = path.relative_to(root)
                zf.write(path, Path(package_root) / rel)
                count += 1
                size += path.stat().st_size
    return {
        "path": str(output),
        "file_count": count,
        "uncompressed_bytes": size,
        "zip_bytes": output.stat().st_size,
    }


def build_package_splits(root: Path, dist_dir: Path) -> dict[str, object]:
    outputs = {
        "source_handoff": build_zip(root, dist_dir / "source_handoff.zip", include_source, "crypto_ai_system_source_handoff"),
        "validation_evidence_bundle": build_zip(root, dist_dir / "validation_evidence_bundle.zip", include_validation, "crypto_ai_system_validation_evidence"),
        "full_audit_archive": build_zip(root, dist_dir / "full_audit_archive.zip", include_full_audit, "crypto_ai_system_full_audit_archive"),
        "runtime_candidate_package": build_zip(root, dist_dir / "runtime_candidate_package.zip", include_runtime, "crypto_ai_system_runtime_candidate"),
        "external_runtime_adapter_package": build_zip(root, dist_dir / "external_runtime_adapter_package.zip", include_external_adapter_package, "crypto_ai_system_p59_external_runtime_adapter_package"),
    }
    manifest = {
        "package_split_version": "p70_venue_neutral_package_split_v1",
        "phase": "P70_VENUE_NEUTRAL_EXECUTION_CONTRACT",
        "primary_execution_venue": "extended",
        "venue_contract_version": "p70_venue_neutral_execution_contract_v1",
        "binance_branch_status": "REFERENCE_ONLY_BINANCE_BRANCH",
        "binance_reference_branch_runtime_enabled": False,
        "cross_venue_evidence_import_allowed": False,
        "review_only": True,
        "runtime_authority_source": False,
        "actual_operator_run_package_received": False,
        "actual_operator_run_package_accepted": False,
        "eligible_for_operator_managed_external_order_test_run": False,
        "actual_redacted_order_test_receipt_received": False,
        "actual_redacted_order_test_receipt_accepted": False,
        "actual_real_order_test_dry_validation_proven": False,
        "eligible_for_next_signed_testnet_submit_preflight": False,
        "p50_external_evidence_import_eligible": False,
        "p7_post_submit_evidence_import_eligible": False,
        "real_order_test_endpoint_call_performed_by_p67": False,
        "sender_execution_performed_by_p68": False,
        "real_order_test_endpoint_call_performed_by_p68": False,
        "order_submission_performed": False,
        "secret_value_accessed": False,
        "source_handoff_excludes_storage": True,
        "runtime_candidate_excludes_generated_storage": True,
        "external_runtime_adapter_package_separate": True,
        "runtime_candidate_excludes_external_adapter_package": True,
        "outputs": outputs,
    }
    manifest_path = dist_dir / "package_split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build P45 source/evidence/audit/runtime package split ZIPs.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--dist-dir", default=DEFAULT_DIST, help="Output directory")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = root / dist_dir
    manifest = build_package_splits(root, dist_dir)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
