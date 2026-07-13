from __future__ import annotations

from pathlib import Path


MAPPINGS = {
    "phase6_signed_testnet_preparation_preview.py":
        "signed_testnet_preparation.py",
    "phase6_1_signed_testnet_operator_unlock_request_template.py":
        "operator_unlock_template.py",
    "phase6_2_operator_unlock_request_fixture_validator.py":
        "operator_unlock_fixtures.py",
    "phase6_3_signed_testnet_readiness_gate_review.py":
        "readiness_gate.py",
    "phase6_4_signed_testnet_readiness_review_packet.py":
        "readiness_packet.py",
    "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py":
        "actual_intake_sandbox.py",
    "phase6_6_actual_intake_validation_bridge.py":
        "actual_intake_bridge.py",
}

LEGACY_PHASE6_PREFIX = "crypto_ai_system.validation." "phase6_"

SCRIPT_IMPORTS = {
    "build_phase6_signed_testnet_preparation_preview.py":
        "crypto_ai_system.governance.signed_testnet_preparation",
    "build_phase6_1_signed_testnet_operator_unlock_request_template.py":
        "crypto_ai_system.governance.operator_unlock_template",
    "build_phase6_2_operator_unlock_request_fixture_validator.py":
        "crypto_ai_system.governance.operator_unlock_fixtures",
    "build_phase6_3_signed_testnet_readiness_gate_review.py":
        "crypto_ai_system.governance.readiness_gate",
    "build_phase6_4_signed_testnet_readiness_review_packet.py":
        "crypto_ai_system.governance.readiness_packet",
    "build_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py":
        "crypto_ai_system.governance.actual_intake_sandbox",
    "build_phase6_6_actual_intake_validation_bridge.py":
        "crypto_ai_system.governance.actual_intake_bridge",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    validation = (
        root
        / "src"
        / "crypto_ai_system"
        / "validation"
    )

    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )

    scripts = root / "scripts"

    blockers: list[str] = []

    for legacy_name, semantic_name in MAPPINGS.items():
        legacy = validation / legacy_name
        semantic = governance / semantic_name

        if not semantic.exists():
            blockers.append(
                f"PHASE6_SEMANTIC_MODULE_MISSING:"
                f"{semantic_name}"
            )

        if not legacy.exists():
            blockers.append(
                f"PHASE6_LEGACY_WRAPPER_MISSING:"
                f"{legacy_name}"
            )
            continue

        text = legacy.read_text(encoding="utf-8")

        if "thin compatibility wrapper" not in text.lower():
            blockers.append(
                f"PHASE6_LEGACY_MODULE_NOT_WRAPPER:"
                f"{legacy_name}"
            )

        if len(text.splitlines()) > 12:
            blockers.append(
                f"PHASE6_LEGACY_WRAPPER_TOO_LARGE:"
                f"{legacy_name}"
            )

    readiness = governance / "readiness.py"

    if not readiness.exists():
        blockers.append(
            "PHASE6_READINESS_AGGREGATOR_MISSING"
        )
    else:
        text = readiness.read_text(encoding="utf-8")

        for semantic_name in MAPPINGS.values():
            module_name = semantic_name.removesuffix(".py")

            expected = (
                "crypto_ai_system.governance."
                + module_name
            )

            if expected not in text:
                blockers.append(
                    "PHASE6_READINESS_SEMANTIC_IMPORT_MISSING:"
                    + module_name
                )

        if LEGACY_PHASE6_PREFIX in text:
            blockers.append(
                "PHASE6_READINESS_IMPORTS_LEGACY_PATH"
            )

    for script_name, semantic_import in SCRIPT_IMPORTS.items():
        path = scripts / script_name

        if not path.exists():
            # Some historical packages may not expose every builder.
            continue

        text = path.read_text(encoding="utf-8")

        if semantic_import not in text:
            blockers.append(
                f"PHASE6_SCRIPT_SEMANTIC_IMPORT_MISSING:"
                f"{script_name}"
            )

        if LEGACY_PHASE6_PREFIX in text:
            blockers.append(
                f"PHASE6_SCRIPT_IMPORTS_LEGACY_PATH:"
                f"{script_name}"
            )

    excluded = {
        validation / name
        for name in MAPPINGS
    }

    for base in (
        root / "src" / "crypto_ai_system",
        scripts,
        root / "run_full_cycle.py",
    ):
        paths = (
            [base]
            if base.is_file()
            else list(base.rglob("*.py"))
        )

        for path in paths:
            if path in excluded:
                continue

            if (
                path.parent == scripts
                and path.name.startswith("check_")
            ):
                continue

            text = path.read_text(encoding="utf-8")

            if LEGACY_PHASE6_PREFIX in text:
                blockers.append(
                    "PHASE6_ACTIVE_LEGACY_IMPORT:"
                    + str(
                        path.relative_to(root)
                    ).replace("\\", "/")
                )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)

        return 2

    print(
        "PHASE6_SEMANTIC_GOVERNANCE_MIGRATION_VALID"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
