from __future__ import annotations

from pathlib import Path


DIRECT_IMPORTS = (
    "crypto_ai_system.validation."
    "phase6_signed_testnet_preparation_preview",
    "crypto_ai_system.validation."
    "phase6_1_signed_testnet_operator_unlock_request_template",
    "crypto_ai_system.validation."
    "phase6_2_operator_unlock_request_fixture_validator",
    "crypto_ai_system.validation."
    "phase6_3_signed_testnet_readiness_gate_review",
    "crypto_ai_system.validation."
    "phase6_4_signed_testnet_readiness_review_packet",
    "crypto_ai_system.validation."
    "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox",
    "crypto_ai_system.validation."
    "phase6_6_actual_intake_validation_bridge",
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    blockers: list[str] = []

    readiness = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "readiness.py"
    )

    if not readiness.exists():
        blockers.append(
            "PHASE6_READINESS_REVIEW_MODULE_MISSING"
        )
    else:
        text = readiness.read_text(encoding="utf-8")

        for required in (
            "run_readiness_review_chain",
            "build_readiness_review_report",
            "WAITING_FOR_MANUAL_ARTIFACTS",
            "ACTUAL_INTAKE_REVIEW_ONLY",
            "BLOCKED",
        ):
            if required not in text:
                blockers.append(
                    f"PHASE6_READINESS_CONTRACT_MISSING:"
                    f"{required}"
                )

    full_cycle = (
        root / "run_full_cycle.py"
    ).read_text(encoding="utf-8")

    expected_import = (
        "from crypto_ai_system.governance.readiness "
        "import run_readiness_review_chain"
    )

    if expected_import not in full_cycle:
        blockers.append(
            "PHASE6_FULL_CYCLE_READINESS_IMPORT_MISSING"
        )

    for direct in DIRECT_IMPORTS:
        if direct in full_cycle:
            blockers.append(
                "PHASE6_FULL_CYCLE_DIRECT_IMPORT_REMAINS:"
                + direct
            )

    if '"readiness_review": readiness_review' not in full_cycle:
        blockers.append(
            "PHASE6_FULL_CYCLE_READINESS_OUTPUT_MISSING"
        )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE6_READINESS_REVIEW_MERGE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
