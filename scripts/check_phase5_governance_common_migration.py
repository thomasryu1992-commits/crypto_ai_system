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


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )
    blockers: list[str] = []

    common = governance / "common.py"
    if not common.exists():
        blockers.append("GOVERNANCE_COMMON_MODULE_MISSING")
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
                    f"GOVERNANCE_COMMON_FORBIDDEN_CONTENT:{forbidden}"
                )

    for name in CANONICAL_MODULES:
        path = governance / name
        if not path.exists():
            blockers.append(
                f"PHASE5_SEMANTIC_MODULE_MISSING:{name}"
            )
            continue

        text = path.read_text(encoding="utf-8")
        if (
            "from crypto_ai_system.governance.common import"
            not in text
        ):
            blockers.append(
                f"GOVERNANCE_COMMON_IMPORT_MISSING:{name}"
            )

        tree = ast.parse(text, filename=str(path))
        defined = {
            node.name
            for node in tree.body
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }
        for helper in sorted(defined & DUPLICATE_HELPERS):
            blockers.append(
                f"DUPLICATE_GOVERNANCE_HELPER:{name}:{helper}"
            )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE5_GOVERNANCE_COMMON_UTILS_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
