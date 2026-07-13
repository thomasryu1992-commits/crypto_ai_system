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


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )

    blockers: list[str] = []

    common = governance / "readiness_common.py"

    if not common.exists():
        blockers.append(
            "READINESS_COMMON_MODULE_MISSING"
        )
    else:
        text = common.read_text(encoding="utf-8")

        for forbidden in (
            "external_runtime_packages",
            "windows_credential_provider",
            "place_order(",
            "cancel_order(",
        ):
            if forbidden in text:
                blockers.append(
                    "READINESS_COMMON_FORBIDDEN_CONTENT:"
                    + forbidden
                )

    for name in CANONICAL_MODULES:
        path = governance / name

        if not path.exists():
            blockers.append(
                f"PHASE6_CANONICAL_MODULE_MISSING:"
                f"{name}"
            )
            continue

        text = path.read_text(encoding="utf-8")

        if (
            "from crypto_ai_system.governance."
            "readiness_common import"
            not in text
        ):
            blockers.append(
                f"READINESS_COMMON_IMPORT_MISSING:"
                f"{name}"
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

        for helper in sorted(
            defined & DUPLICATE_HELPERS
        ):
            blockers.append(
                f"DUPLICATE_READINESS_HELPER:"
                f"{name}:{helper}"
            )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)

        return 2

    print(
        "PHASE6_READINESS_COMMON_UTILS_VALID"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
