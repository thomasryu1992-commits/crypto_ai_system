from __future__ import annotations

import json
from pathlib import Path


MODULE_MAP = {
    "phase5_manual_approval_intake_validation.py":
        "approval_intake.py",
    "phase5_1_manual_approval_operator_handoff.py":
        "operator_handoff.py",
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

FORBIDDEN_TRUE = {
    "runtime_permission_source",
    "approval_intake_validated",
    "approval_packet_created",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "auto_promotion_allowed",
    "signed_testnet_unlock_allowed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    governance = root / "src" / "crypto_ai_system" / "governance"
    validation = root / "src" / "crypto_ai_system" / "validation"
    scripts = root / "scripts"
    blockers: list[str] = []

    required_modules = {
        "common.py",
        "approval.py",
        "approval_intake.py",
        "operator_handoff.py",
        "approval_fixtures.py",
    }

    for name in sorted(required_modules):
        if not (governance / name).exists():
            blockers.append(
                f"PHASE5_CANONICAL_MODULE_MISSING:{name}"
            )

    for legacy_name, semantic_name in MODULE_MAP.items():
        legacy = validation / legacy_name
        semantic = governance / semantic_name

        if not semantic.exists():
            blockers.append(
                f"PHASE5_CANONICAL_MODULE_MISSING:{semantic_name}"
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

    for script_name, semantic_import in SCRIPT_IMPORTS.items():
        path = scripts / script_name

        if not path.exists():
            blockers.append(
                f"PHASE5_COMPAT_SCRIPT_MISSING:{script_name}"
            )
            continue

        text = path.read_text(encoding="utf-8")

        if semantic_import not in text:
            blockers.append(
                f"PHASE5_SCRIPT_SEMANTIC_IMPORT_MISSING:"
                f"{script_name}"
            )

        if LEGACY_PHASE5_PREFIX in text:
            blockers.append(
                f"PHASE5_SCRIPT_STILL_IMPORTS_LEGACY_PATH:"
                f"{script_name}"
            )

    excluded = {
        validation / name
        for name in MODULE_MAP
    }

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

    approval = governance / "approval.py"

    if approval.exists():
        text = approval.read_text(encoding="utf-8")

        if "run_approval_review_chain" not in text:
            blockers.append(
                "PHASE5_UNIFIED_APPROVAL_ENTRY_MISSING"
            )

        for state in (
            "WAITING_FOR_HUMAN",
            "SUBMITTED_REVIEW_ONLY",
            "BLOCKED",
        ):
            if state not in text:
                blockers.append(
                    f"PHASE5_APPROVAL_STATE_MISSING:{state}"
                )

    full_cycle = (root / "run_full_cycle.py").read_text(
        encoding="utf-8"
    )

    if (
        "from crypto_ai_system.governance.approval "
        "import run_approval_review_chain"
    ) not in full_cycle:
        blockers.append(
            "PHASE5_FULL_CYCLE_UNIFIED_ENTRY_MISSING"
        )

    if '"approval_review": approval_review' not in full_cycle:
        blockers.append(
            "PHASE5_FULL_CYCLE_APPROVAL_OUTPUT_MISSING"
        )

    closure_path = (
        root / "config" / "lean" / "phase5_lean_closure.json"
    )

    if not closure_path.exists():
        blockers.append("PHASE5_CLOSURE_MANIFEST_MISSING")
    else:
        payload = json.loads(
            closure_path.read_text(encoding="utf-8")
        )

        if payload.get("status") != "PHASE5_LEAN_MERGE_CLOSED":
            blockers.append(
                "PHASE5_CLOSURE_STATUS_INVALID"
            )

        if payload.get("runtime_authority") is not False:
            blockers.append(
                "PHASE5_RUNTIME_AUTHORITY_MUST_BE_FALSE"
            )

        if payload.get("next_work") != "PHASE6_READINESS_MERGE":
            blockers.append(
                "PHASE5_NEXT_WORK_INVALID"
            )

        safety = payload.get("safety") or {}

        for flag in sorted(FORBIDDEN_TRUE):
            if safety.get(flag) is not False:
                blockers.append(
                    f"PHASE5_UNSAFE_CLOSURE_FLAG:{flag}"
                )

    migration_path = (
        root
        / "config"
        / "lean"
        / "lean_migration_state.json"
    )

    if not migration_path.exists():
        blockers.append(
            "LEAN_MIGRATION_STATE_MISSING"
        )
    else:
        migration = json.loads(
            migration_path.read_text(encoding="utf-8")
        )

        phase5 = (
            migration.get("completed", {})
            .get("phase5_approval", {})
        )

        if phase5.get("status") != "CLOSED":
            blockers.append(
                "LEAN_MIGRATION_PHASE5_NOT_CLOSED"
            )

        current = migration.get("current", {})

        if current.get("target") != "PHASE7_EXECUTOR_REVIEW_MERGE":
            blockers.append(
                "LEAN_MIGRATION_NEXT_TARGET_INVALID"
            )

        if migration.get("execution_permissions_changed") is not False:
            blockers.append(
                "LEAN_MIGRATION_PERMISSION_CHANGE_INVALID"
            )

    history = (
        root
        / "docs"
        / "history"
        / "PHASE5_APPROVAL_DEVELOPMENT_SUMMARY.md"
    )

    if not history.exists():
        blockers.append(
            "PHASE5_CONSOLIDATED_HISTORY_MISSING"
        )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("PHASE5_LEAN_CLOSURE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
