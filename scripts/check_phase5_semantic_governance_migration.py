from __future__ import annotations

from pathlib import Path


MAPPINGS = {
    "phase5_manual_approval_intake_validation.py": "approval_intake.py",
    "phase5_1_manual_approval_operator_handoff.py": "operator_handoff.py",
    "phase5_2_manual_approval_submission_fixture_validator.py":
        "approval_fixtures.py",
}

LEGACY_PHASE5_PREFIX = "crypto_ai_system.validation." "phase5_"

SCRIPT_IMPORTS = {
    "build_phase5_manual_approval_intake_validation.py":
        "crypto_ai_system.governance.approval_intake",
    "build_phase5_1_manual_approval_operator_handoff.py":
        "crypto_ai_system.governance.operator_handoff",
    "build_phase5_2_manual_approval_submission_fixture_validator.py":
        "crypto_ai_system.governance.approval_fixtures",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    validation = root / "src" / "crypto_ai_system" / "validation"
    governance = root / "src" / "crypto_ai_system" / "governance"
    blockers: list[str] = []

    for legacy_name, semantic_name in MAPPINGS.items():
        legacy = validation / legacy_name
        semantic = governance / semantic_name

        if not semantic.exists():
            blockers.append(
                f"PHASE5_SEMANTIC_MODULE_MISSING:{semantic_name}"
            )

        if not legacy.exists():
            blockers.append(
                f"PHASE5_LEGACY_WRAPPER_MISSING:{legacy_name}"
            )
            continue

        text = legacy.read_text(encoding="utf-8")
        if "thin compatibility wrapper" not in text.lower():
            blockers.append(
                f"PHASE5_LEGACY_MODULE_NOT_WRAPPER:{legacy_name}"
            )
        if len(text.splitlines()) > 12:
            blockers.append(
                f"PHASE5_LEGACY_WRAPPER_TOO_LARGE:{legacy_name}"
            )

    approval = governance / "approval.py"
    if not approval.exists():
        blockers.append("PHASE5_APPROVAL_AGGREGATOR_MISSING")
    else:
        text = approval.read_text(encoding="utf-8")
        for semantic in (
            "crypto_ai_system.governance.approval_intake",
            "crypto_ai_system.governance.operator_handoff",
            "crypto_ai_system.governance.approval_fixtures",
        ):
            if semantic not in text:
                blockers.append(
                    f"PHASE5_APPROVAL_SEMANTIC_IMPORT_MISSING:{semantic}"
                )
        if LEGACY_PHASE5_PREFIX in text:
            blockers.append(
                "PHASE5_APPROVAL_AGGREGATOR_IMPORTS_LEGACY_PATH"
            )

    scripts = root / "scripts"
    for name, semantic in SCRIPT_IMPORTS.items():
        path = scripts / name
        if not path.exists():
            blockers.append(f"PHASE5_COMPAT_SCRIPT_MISSING:{name}")
            continue
        text = path.read_text(encoding="utf-8")
        if semantic not in text:
            blockers.append(
                f"PHASE5_SCRIPT_SEMANTIC_IMPORT_MISSING:{name}"
            )
        if LEGACY_PHASE5_PREFIX in text:
            blockers.append(
                f"PHASE5_SCRIPT_IMPORTS_LEGACY_PATH:{name}"
            )

    excluded = {validation / name for name in MAPPINGS}
    for base in (
        root / "src" / "crypto_ai_system",
        scripts,
        root / "run_full_cycle.py",
    ):
        paths = [base] if base.is_file() else list(base.rglob("*.py"))
        for path in paths:
            if path in excluded or path.name.startswith("check_"):
                continue
            text = path.read_text(encoding="utf-8")
            if LEGACY_PHASE5_PREFIX in text:
                blockers.append(
                    "PHASE5_ACTIVE_LEGACY_IMPORT:"
                    + str(path.relative_to(root)).replace("\\", "/")
                )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE5_SEMANTIC_GOVERNANCE_MIGRATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
