from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def validate() -> dict:
    errors: list[str] = []
    required = (
        "src/crypto_ai_system/validation/p71_extended_readonly_closure.py",
        "scripts/build_p71_extended_readonly_closure.py",
        "scripts/merge_p71_extended_readonly_evidence.py",
        "scripts/run_p71_live_readonly_closure.ps1",
        "scripts/check_p71_closure_contract.py",
        "tests/test_p71_extended_readonly_closure.py",
        "docs/P71_EXTENDED_TESTNET_READ_ONLY_CLOSURE_RUNBOOK.md",
        ".github/workflows/p71_public_live_probe.yml",
        ".github/workflows/review_only_chain_validation.yml",
    )
    for rel in required:
        if not (ROOT / rel).exists():
            errors.append(f"required_path_missing:{rel}")
    if errors:
        return {"passed": False, "status": "P71_CLOSURE_CONTRACT_BLOCKED", "errors": errors}

    source = _read("src/crypto_ai_system/validation/p71_extended_readonly_closure.py")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("external_runtime_packages"):
            errors.append("closure_core_imports_external_credential_package")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("external_runtime_packages"):
                    errors.append("closure_core_imports_external_credential_package")

    for token in (
        'P71_CLOSURE_VERSION = "p71_extended_readonly_closure_v1"',
        "P71_MAX_SOURCE_SKEW_SECONDS = 180",
        "build_p71_complete_evidence",
        "p71_consumed_evidence_registry.jsonl",
        "closure_evidence_consumed",
        "ready_for_signed_testnet_execution\": False",
        "testnet_order_submission_allowed\": False",
    ):
        if token not in source:
            errors.append(f"closure_source_missing_token:{token}")

    powershell = _read("scripts/run_p71_live_readonly_closure.ps1")
    for forbidden in ("--api-key", "--private-key", "StarkPrivateKey", "ApiKeyValue"):
        if forbidden in powershell:
            errors.append(f"powershell_accepts_or_names_secret_value:{forbidden}")
    for required_token in (
        "--credential-target",
        "--credential-reference-id",
        "run_p71_extended_public_probe.py",
        "build_p71_extended_readonly_closure.py",
    ):
        if required_token not in powershell:
            errors.append(f"powershell_missing_token:{required_token}")

    manual_workflow = _read(".github/workflows/p71_public_live_probe.yml")
    if "workflow_dispatch:" not in manual_workflow:
        errors.append("manual_public_probe_missing_workflow_dispatch")
    if "pull_request:" in manual_workflow or "push:" in manual_workflow:
        errors.append("manual_public_probe_must_not_run_on_push_or_pr")
    if "contents: read" not in manual_workflow:
        errors.append("manual_public_probe_permissions_not_read_only")
    if "secrets." in manual_workflow:
        errors.append("manual_public_probe_must_not_use_repository_secrets")

    main_workflow = _read(".github/workflows/review_only_chain_validation.yml")
    for command in (
        "python -m pytest -q tests/test_p71_extended_readonly_closure.py",
        "python scripts/check_p71_closure_contract.py",
    ):
        if command not in main_workflow:
            errors.append(f"main_workflow_missing_closure_command:{command}")

    doc = _read("docs/P71_EXTENDED_TESTNET_READ_ONLY_CLOSURE_RUNBOOK.md")
    for wording in (
        "P71 remains incomplete until",
        "Windows Credential Manager",
        "p71_complete=true",
        "ready_for_signed_testnet_execution=false",
        "testnet_order_submission_allowed=false",
    ):
        if wording not in doc:
            errors.append(f"closure_runbook_missing_wording:{wording}")

    return {
        "passed": not errors,
        "status": "P71_CLOSURE_CONTRACT_PASSED" if not errors else "P71_CLOSURE_CONTRACT_BLOCKED",
        "errors": sorted(set(errors)),
        "p71_complete": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
