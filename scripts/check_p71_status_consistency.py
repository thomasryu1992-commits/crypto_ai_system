from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_STATUS = "public_and_private_rest_valid_public_and_private_websocket_live_evidence_pending"
EXPECTED_PUBLIC_VERSION = "p71_extended_testnet_read_only_connectivity_v3"
EXPECTED_PRIVATE_VERSION = "p71_extended_private_read_only_receipt_v2"

REQUIRED_STATUS_WORDING = (
    "P71 remains incomplete",
    "public REST evidence is valid",
    "private account REST evidence is valid",
    "public WebSocket live evidence is pending",
    "private account WebSocket live evidence is pending",
    "p71_complete=false",
    "testnet_order_submission_allowed=false",
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_yaml(path: str) -> dict[str, Any]:
    return yaml.safe_load(_read(path)) or {}


def _check_core_import_boundary(errors: list[str]) -> None:
    src_root = ROOT / "src" / "crypto_ai_system"
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"core_ast_parse_failed:{path.relative_to(ROOT)}:{exc.lineno}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                modules = []
            for module in modules:
                if module.startswith("external_runtime_packages"):
                    errors.append(f"core_imports_credential_process:{path.relative_to(ROOT)}:{module}")
                if "windows_credential_provider" in module:
                    errors.append(f"core_imports_windows_credential_provider:{path.relative_to(ROOT)}:{module}")
        if "X-Api-Key" in text:
            errors.append(f"core_contains_credential_header_literal:{path.relative_to(ROOT)}")


def validate() -> dict[str, Any]:
    errors: list[str] = []
    required_paths = (
        "README.md",
        "CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md",
        "docs/P71_EXTENDED_TESTNET_READ_ONLY_CONNECTIVITY.md",
        "config/settings.yaml",
        "src/crypto_ai_system/execution/extended_read_only_connectivity.py",
        "external_runtime_packages/extended_read_only_probe/probe.py",
        "external_runtime_packages/extended_read_only_probe/run_windows_probe.py",
        ".github/workflows/review_only_chain_validation.yml",
        "src/crypto_ai_system/validation/p71_extended_readonly_closure.py",
        "scripts/build_p71_extended_readonly_closure.py",
        "scripts/run_p71_live_readonly_closure.ps1",
        "scripts/check_p71_closure_contract.py",
        "docs/P71_EXTENDED_TESTNET_READ_ONLY_CLOSURE_RUNBOOK.md",
        ".github/workflows/p71_public_live_probe.yml",
    )
    for rel in required_paths:
        if not (ROOT / rel).exists():
            errors.append(f"required_path_missing:{rel}")
    if errors:
        return {"passed": False, "errors": errors}

    readme = _read("README.md")
    master = _read("CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md")
    p71_doc = _read("docs/P71_EXTENDED_TESTNET_READ_ONLY_CONNECTIVITY.md")
    settings = _load_yaml("config/settings.yaml")
    workflow = _read(".github/workflows/review_only_chain_validation.yml")
    public_source = _read("src/crypto_ai_system/execution/extended_read_only_connectivity.py")
    private_source = _read("external_runtime_packages/extended_read_only_probe/probe.py")
    private_cli = _read("external_runtime_packages/extended_read_only_probe/run_windows_probe.py")

    p71 = settings.get("p71_extended_read_only") or {}
    expected_flags = {
        "public_rest_evidence_valid": True,
        "private_account_rest_evidence_valid": True,
        "public_websocket_contract_hardened": True,
        "private_account_websocket_contract_hardened": True,
        "public_websocket_live_evidence_valid": False,
        "private_account_websocket_live_evidence_valid": False,
        "p71_complete": False,
        "api_key_value_allowed_in_core": False,
        "write_calls_allowed": False,
        "order_endpoint_allowed": False,
        "cancel_endpoint_allowed": False,
        "signature_allowed": False,
        "stark_private_key_access_allowed": False,
        "testnet_order_submission_allowed": False,
    }
    if p71.get("status") != EXPECTED_STATUS:
        errors.append("settings_p71_status_mismatch")
    if p71.get("public_contract_version") != EXPECTED_PUBLIC_VERSION:
        errors.append("settings_p71_public_version_mismatch")
    if p71.get("private_receipt_version") != EXPECTED_PRIVATE_VERSION:
        errors.append("settings_p71_private_version_mismatch")
    for field, expected in expected_flags.items():
        if p71.get(field) is not expected:
            errors.append(f"settings_p71_flag_mismatch:{field}")

    for wording in REQUIRED_STATUS_WORDING:
        for name, text in (("readme", readme), ("master", master), ("p71_doc", p71_doc)):
            if wording not in text:
                errors.append(f"{name}_missing_p71_wording:{wording}")

    for token in (
        f'P71_VERSION = "{EXPECTED_PUBLIC_VERSION}"',
        f'P71_PRIVATE_RECEIPT_VERSION = "{EXPECTED_PRIVATE_VERSION}"',
        "P71_HEARTBEAT_OBSERVATION_SECONDS = 27",
        '"INFERRED_FROM_CONNECTION_SURVIVAL"',
        "P71_MARKET_RULE_MAX_AGE_MS",
        "P71_ORDERBOOK_MAX_AGE_MS",
        "P71_EVIDENCE_MAX_AGE_SECONDS",
        "P71_PRIVATE_RECEIPT_HASH_MISMATCH",
        "P71_PUBLIC_EVIDENCE_HASH_MISMATCH",
    ):
        if token not in public_source:
            errors.append(f"public_source_missing_contract_token:{token}")

    for token in (
        f'P71_PRIVATE_RECEIPT_VERSION = "{EXPECTED_PRIVATE_VERSION}"',
        "websocket_private_account_snapshot_probe",
        "allow_redirects=False",
        "DOCUMENTED_BALANCE_404_AFTER_ACTIVE_ACCOUNT_AUTH",
        "rest_ws_consistency_valid",
        "receipt_sha256",
    ):
        if token not in private_source:
            errors.append(f"private_source_missing_contract_token:{token}")

    for forbidden in ("--api-key", "--private-key"):
        if forbidden in private_cli:
            errors.append(f"private_cli_accepts_secret_argument:{forbidden}")
    if "read_generic_credential_secret" not in private_cli:
        errors.append("private_cli_missing_os_credential_provider")

    for command in (
        "python -m pytest -q tests/test_p71_extended_read_only_connectivity.py",
        "python scripts/check_p71_status_consistency.py",
        "python -m pytest -q tests/test_p71_extended_readonly_closure.py",
        "python scripts/check_p71_closure_contract.py",
    ):
        if command not in workflow:
            errors.append(f"workflow_missing_p71_command:{command}")

    closure_source = _read("src/crypto_ai_system/validation/p71_extended_readonly_closure.py")
    for token in (
        'P71_CLOSURE_VERSION = "p71_extended_readonly_closure_v1"',
        "P71_MAX_SOURCE_SKEW_SECONDS = 180",
        "p71_consumed_evidence_registry.jsonl",
        '"ready_for_signed_testnet_execution": False',
        '"testnet_order_submission_allowed": False',
    ):
        if token not in closure_source:
            errors.append(f"closure_source_missing_contract_token:{token}")

    _check_core_import_boundary(errors)

    safety = settings.get("safety") or {}
    if safety.get("live_trading_enabled") is not False:
        errors.append("safety_live_trading_not_false")
    if safety.get("testnet_signed_order_enabled") is not False:
        errors.append("safety_testnet_signed_order_not_false")

    result = {
        "passed": not errors,
        "status": "P71_STATUS_CONSISTENCY_PASSED" if not errors else "P71_STATUS_CONSISTENCY_BLOCKED",
        "errors": sorted(set(errors)),
        "expected_status": EXPECTED_STATUS,
        "expected_public_version": EXPECTED_PUBLIC_VERSION,
        "expected_private_version": EXPECTED_PRIVATE_VERSION,
        "p71_complete": False,
        "testnet_order_submission_allowed": False,
        "ready_for_signed_testnet_execution": False,
    }
    return result


def main() -> int:
    result = validate()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
