from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    blockers: list[str] = []

    approval = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "approval.py"
    )
    if not approval.exists():
        blockers.append("APPROVAL_REVIEW_MODULE_MISSING")
    else:
        text = approval.read_text(encoding="utf-8")
        for required in (
            "run_approval_review_chain",
            "build_approval_review_report",
            "STATE_WAITING_FOR_HUMAN",
            "STATE_SUBMITTED_REVIEW_ONLY",
            "STATE_BLOCKED",
        ):
            if required not in text:
                blockers.append(f"APPROVAL_REVIEW_CONTRACT_MISSING:{required}")

    full_cycle = (root / "run_full_cycle.py").read_text(encoding="utf-8")
    if (
        "from crypto_ai_system.governance.approval "
        "import run_approval_review_chain"
    ) not in full_cycle:
        blockers.append("FULL_CYCLE_APPROVAL_REVIEW_IMPORT_MISSING")

    direct_imports = (
        "from crypto_ai_system.validation."
        "phase5_manual_approval_intake_validation",
        "from crypto_ai_system.validation."
        "phase5_1_manual_approval_operator_handoff",
        "from crypto_ai_system.validation."
        "phase5_2_manual_approval_submission_fixture_validator",
    )
    for direct in direct_imports:
        if direct in full_cycle:
            blockers.append("FULL_CYCLE_DIRECT_PHASE5_IMPORT_REMAINS")

    if '"approval_review": approval_review' not in full_cycle:
        blockers.append("FULL_CYCLE_APPROVAL_REVIEW_OUTPUT_MISSING")

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE5_APPROVAL_REVIEW_MERGE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
