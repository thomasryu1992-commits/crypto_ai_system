from __future__ import annotations

import json
from pathlib import Path


FORBIDDEN_TRUE = {
    "runtime_permission_source",
    "operator_decision_runtime_authority",
    "stage_transition_authority",
    "executor_enablement_authority",
    "executor_approval_authority",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_executor_approval_authority",
    "signed_testnet_execution_authority",
    "signed_testnet_order_submission_authority",
    "signed_testnet_promotion_authority",
    "actual_stage_transition_performed",
    "actual_executor_approval_created",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "actual_cancel_performed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "exchange_endpoint_called",
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
    "live_trading_allowed",
    "auto_promotion_allowed",
}


def main() -> int:
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    blockers: list[str] = []

    module = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "pre_executor_review.py"
    )

    if not module.exists():
        blockers.append(
            "PHASE7_15_17_PRE_EXECUTOR_REVIEW_MODULE_MISSING"
        )

    else:
        text = module.read_text(
            encoding="utf-8"
        )

        for required in (
            "run_pre_executor_review_chain",
            "build_operator_decision_intake_template",
            "validate_operator_decision_intake",
            "build_final_pre_executor_review_packet",
            "build_pre_executor_review_report",
            "WAITING_FOR_OPERATOR_DECISION",
            "OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY",
            "OPERATOR_DECISION_DEFERRED_REVIEW_ONLY",
            "OPERATOR_DECISION_REJECTED_REVIEW_ONLY",
            "BLOCKED",
            "do_not_write_automatically",
            "OPERATOR_DECISION_SUBMISSION_MISSING",
            "operator_decision_is_runtime_authority",
            "phase8_execution_allowed",
            "phase8_order_submission_allowed",
        ):
            if required not in text:
                blockers.append(
                    "PHASE7_15_17_PRE_EXECUTOR_CONTRACT_MISSING:"
                    + required
                )

        if (
            "valid_review_only_fixture"
            in text
        ):
            blockers.append(
                "PHASE7_15_17_VALID_FIXTURE_FALLBACK_FORBIDDEN"
            )

    full_cycle_path = (
        root
        / "run_full_cycle.py"
    )

    if not full_cycle_path.exists():
        blockers.append(
            "RUN_FULL_CYCLE_MISSING"
        )

    else:
        full_cycle = (
            full_cycle_path.read_text(
                encoding="utf-8"
            )
        )

        expected_import = (
            "from crypto_ai_system.governance.pre_executor_review "
            "import run_pre_executor_review_chain"
        )

        if (
            expected_import
            not in full_cycle
        ):
            blockers.append(
                "PHASE7_15_17_FULL_CYCLE_IMPORT_MISSING"
            )

        for expected in (
            (
                '"phase7_15_operator_decision_intake_template": '
                "phase7_15_operator_decision_intake_template"
            ),
            (
                '"phase7_16_operator_decision_intake_validation": '
                "phase7_16_operator_decision_intake_validation"
            ),
            (
                '"phase7_17_final_pre_executor_review_packet": '
                "phase7_17_final_pre_executor_review_packet"
            ),
            (
                '"pre_executor_review": '
                "pre_executor_review"
            ),
        ):
            if expected not in full_cycle:
                blockers.append(
                    "PHASE7_15_17_FULL_CYCLE_OUTPUT_MISSING:"
                    + expected
                )

    # Numbered modules remain import-compatible for the pre-merge Phase 8
    # regression suite. They must not remain active orchestration paths.
    if full_cycle_path.exists():
        numbered_imports = (
            "crypto_ai_system.validation.phase7_15_",
            "crypto_ai_system.validation.phase7_16_",
            "crypto_ai_system.validation.phase7_17_",
        )
        for numbered_import in numbered_imports:
            if numbered_import in full_cycle:
                blockers.append(
                    "PHASE7_15_17_ACTIVE_NUMBERED_IMPORT_FORBIDDEN:"
                    + numbered_import
                )

    milestone_path = (
        root
        / "config"
        / "lean"
        / "phase7_15_17_pre_executor_review.json"
    )

    if not milestone_path.exists():
        blockers.append(
            "PHASE7_15_17_MILESTONE_MANIFEST_MISSING"
        )

    else:
        payload = json.loads(
            milestone_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            payload.get(
                "status"
            )
            != (
                "PHASE7_15_17_PRE_EXECUTOR_REVIEW_MERGED"
            )
        ):
            blockers.append(
                "PHASE7_15_17_MILESTONE_STATUS_INVALID"
            )

        if (
            payload.get(
                "runtime_authority"
            )
            is not False
        ):
            blockers.append(
                "PHASE7_15_17_RUNTIME_AUTHORITY_MUST_BE_FALSE"
            )

        manual_policy = (
            payload.get(
                "manual_intake_policy"
            )
            or {}
        )

        for field in (
            "template_writes_submission_automatically",
            "valid_fixture_can_replace_operator_submission",
            "operator_decision_is_runtime_authority",
            "operator_decision_can_transition_stage",
            "operator_decision_can_enable_executor",
            "operator_decision_can_submit_order",
        ):
            if (
                manual_policy.get(
                    field
                )
                is not False
            ):
                blockers.append(
                    "PHASE7_15_17_MANUAL_INTAKE_POLICY_INVALID:"
                    + field
                )

        phase8_boundary = (
            payload.get(
                "phase8_boundary"
            )
            or {}
        )

        for field in (
            "phase8_execution_allowed",
            "phase8_write_path_allowed",
            "phase8_secret_value_handling_allowed",
            "phase8_executor_enablement_allowed",
            "phase8_order_submission_allowed",
        ):
            if (
                phase8_boundary.get(
                    field
                )
                is not False
            ):
                blockers.append(
                    "PHASE7_15_17_PHASE8_BOUNDARY_INVALID:"
                    + field
                )

        safety = (
            payload.get(
                "safety"
            )
            or {}
        )

        for flag in sorted(
            FORBIDDEN_TRUE
        ):
            if (
                safety.get(
                    flag
                )
                is not False
            ):
                blockers.append(
                    "PHASE7_15_17_UNSAFE_MILESTONE_FLAG:"
                    + flag
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
            migration_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            migration.get(
                "current",
                {},
            ).get(
                "next_step"
            )
            not in {
                "PHASE7_LEAN_CLOSURE",
                "PHASE8_SIGNED_TESTNET_EXECUTION_PREPARATION",
                (
                    "PHASE8_M2_METADATA_KEY_SCOPE_"
                    "AND_WRITE_PATH_DRY_VALIDATION"
                ),
            }
        ):
            blockers.append(
                "PHASE7_15_17_NEXT_STEP_INVALID"
            )

        if (
            migration.get(
                "execution_permissions_changed"
            )
            is not False
        ):
            blockers.append(
                "PHASE7_15_17_EXECUTION_PERMISSION_CHANGE_INVALID"
            )

    if blockers:
        for blocker in sorted(
            set(
                blockers
            )
        ):
            print(
                blocker
            )

        return 2

    print(
        "PHASE7_15_17_PRE_EXECUTOR_REVIEW_MERGE_VALID"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
