from __future__ import annotations

import ast
from pathlib import Path


CANONICAL_MODULES = (
    "readiness.py",
    "signed_testnet_preparation.py",
    "operator_unlock_template.py",
    "operator_unlock_fixtures.py",
    "readiness_gate.py",
    "readiness_packet.py",
    "actual_intake_sandbox.py",
    "actual_intake_bridge.py",
)

DUPLICATE_HELPERS = {
    "_latest_dir",
    "_storage_dir",
    "_read_latest_json",
    "_read_optional_json",
    "_safe_text",
    "_safe_bool",
    "_as_positive_float",
    "_as_positive_int",
    "_positive_number",
    "_positive_int",
    "_manual_value_filled",
    "_payload_hash",
    "_artifact_hash",
    "_artifact_summary",
    "_source_summary",
    "_unsafe_fields",
    "_unsafe_flags_by_artifact",
    "_manual_file_summary",
    "_actual_file_summary",
}


def test_phase6_modules_use_shared_readiness_common() -> None:
    root = Path(__file__).resolve().parents[1]

    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )

    for name in CANONICAL_MODULES:
        path = governance / name

        assert path.exists(), path

        text = path.read_text(encoding="utf-8")

        assert (
            "from crypto_ai_system.governance."
            "readiness_common import"
            in text
        )

        tree = ast.parse(
            text,
            filename=str(path),
        )

        defined = {
            node.name
            for node in tree.body
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        }

        assert not (
            defined & DUPLICATE_HELPERS
        ), (
            name,
            defined & DUPLICATE_HELPERS,
        )


def test_readiness_common_has_no_execution_or_secret_provider_imports() -> None:
    root = Path(__file__).resolve().parents[1]

    text = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "readiness_common.py"
    ).read_text(encoding="utf-8")

    assert "external_runtime_packages" not in text
    assert "windows_credential_provider" not in text
    assert "place_order(" not in text
    assert "cancel_order(" not in text
    assert "os.environ" not in text
    assert "getenv(" not in text
    assert "read_secret" not in text.lower()
    assert "create_secret" not in text.lower()
