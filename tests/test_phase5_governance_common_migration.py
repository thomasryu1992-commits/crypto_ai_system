from __future__ import annotations

import ast
from pathlib import Path


CANONICAL_MODULES = (
    "approval_intake.py",
    "operator_handoff.py",
    "approval_fixtures.py",
)

DUPLICATE_HELPERS = {
    "_latest_dir",
    "_storage_dir",
    "_read_latest_json",
    "_safe_text",
    "_hash_payload_without",
    "_verify_embedded_hash",
}


def test_phase5_modules_use_shared_governance_common() -> None:
    root = Path(__file__).resolve().parents[1]
    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )

    for name in CANONICAL_MODULES:
        path = governance / name
        text = path.read_text(encoding="utf-8")
        assert "from crypto_ai_system.governance.common import" in text

        tree = ast.parse(text)
        defined = {
            node.name
            for node in tree.body
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }
        assert not (defined & DUPLICATE_HELPERS), (
            name,
            defined & DUPLICATE_HELPERS,
        )


def test_governance_common_has_no_execution_or_secret_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "common.py"
    ).read_text(encoding="utf-8")

    assert "external_runtime_packages" not in text
    assert "windows_credential_provider" not in text
    assert "place_order(" not in text
    assert "cancel_order(" not in text
