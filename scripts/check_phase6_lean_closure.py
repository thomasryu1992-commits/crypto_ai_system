from __future__ import annotations

import json
from pathlib import Path


MODULE_MAP = {
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

FORBIDDEN_TRUE = {
    "runtime_permission_source",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "approval_intake_validated",
    "operator_unlock_request_validated",
    "signed_testnet_preparation_ready",
    "signed_testnet_readiness_passed",
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
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "auto_promotion_allowed",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    governance = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
    )

    validation = (
        root
        / "src"
        / "crypto_ai_system"
        / "validation"
    )

    scripts = root / "scripts"

    blockers: list[str] = []

    required_modules = {
        "readiness_common.py",
        "readiness.py",
        "signed_testnet_preparation.py",
        "operator_unlock_template.py",
        "operator_unlock_fixtures.py",
        "readiness_gate.py",
        "readiness_packet.py",
        "actual_intake_sandbox.py",
        "actual_intake_bridge.py",
    }

    for name in sorted(required_modules):
        if not (governance / name).exists():
            blockers.append(
                f"PHASE6_CANONICAL_MODULE_MISSING:"
                f"{name}"
            )

    for legacy_name, semantic_name in MODULE_MAP.items():
        legacy = validation / legacy_name
        semantic = governance / semantic_name

        if not semantic.exists():
            blockers.append(
                f"PHASE6_CANONICAL_MODULE_MISSING:"
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

    excluded = {
        validation / name
        for name in MODULE_MAP
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

    readiness = governance / "readiness.py"

    if readiness.exists():
        text = readiness.read_text(encoding="utf-8")

        if "run_readiness_review_chain" not in text:
            blockers.append(
                "PHASE6_UNIFIED_READINESS_ENTRY_MISSING"
            )

        for state in (
            "WAITING_FOR_MANUAL_ARTIFACTS",
            "ACTUAL_INTAKE_REVIEW_ONLY",
            "BLOCKED",
        ):
            if state not in text:
                blockers.append(
                    f"PHASE6_READINESS_STATE_MISSING:"
                    f"{state}"
                )

    full_cycle = (
        root / "run_full_cycle.py"
    ).read_text(encoding="utf-8")

    if (
        "from crypto_ai_system.governance.readiness "
        "import run_readiness_review_chain"
    ) not in full_cycle:
        blockers.append(
            "PHASE6_FULL_CYCLE_UNIFIED_ENTRY_MISSING"
        )

    if '"readiness_review": readiness_review' not in full_cycle:
        blockers.append(
            "PHASE6_FULL_CYCLE_READINESS_OUTPUT_MISSING"
        )

    closure_path = (
        root
        / "config"
        / "lean"
        / "phase6_lean_closure.json"
    )

    if not closure_path.exists():
        blockers.append(
            "PHASE6_CLOSURE_MANIFEST_MISSING"
        )
    else:
        payload = json.loads(
            closure_path.read_text(encoding="utf-8")
        )

        if (
            payload.get("status")
            != "PHASE6_LEAN_MERGE_CLOSED"
        ):
            blockers.append(
                "PHASE6_CLOSURE_STATUS_INVALID"
            )

        if payload.get("runtime_authority") is not False:
            blockers.append(
                "PHASE6_RUNTIME_AUTHORITY_MUST_BE_FALSE"
            )

        if (
            payload.get("next_work")
            != "PHASE7_EXECUTOR_REVIEW_MERGE"
        ):
            blockers.append(
                "PHASE6_NEXT_WORK_INVALID"
            )

        safety = payload.get("safety") or {}

        for flag in sorted(FORBIDDEN_TRUE):
            if safety.get(flag) is not False:
                blockers.append(
                    f"PHASE6_UNSAFE_CLOSURE_FLAG:"
                    f"{flag}"
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

        phase6 = (
            migration
            .get("completed", {})
            .get("phase6_readiness", {})
        )

        if phase6.get("status") != "CLOSED":
            blockers.append(
                "LEAN_MIGRATION_PHASE6_NOT_CLOSED"
            )

        current = migration.get("current", {})

        if (
            current.get("target")
            != "PHASE7_EXECUTOR_REVIEW_MERGE"
        ):
            blockers.append(
                "LEAN_MIGRATION_NEXT_TARGET_INVALID"
            )

        if (
            migration.get(
                "execution_permissions_changed"
            )
            is not False
        ):
            blockers.append(
                "LEAN_MIGRATION_PERMISSION_CHANGE_INVALID"
            )

    history = (
        root
        / "docs"
        / "history"
        / "PHASE6_READINESS_DEVELOPMENT_SUMMARY.md"
    )

    if not history.exists():
        blockers.append(
            "PHASE6_CONSOLIDATED_HISTORY_MISSING"
        )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)

        return 2

    print("PHASE6_LEAN_CLOSURE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
