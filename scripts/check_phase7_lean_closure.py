from __future__ import annotations

import ast
import json
from pathlib import Path


STEP_MAPPINGS = {
    "phase7_signed_testnet_validation_design_guard.py": (
        "validation_design.py"
    ),
    "phase7_1_signed_testnet_pre_submit_payload_guard.py": (
        "pre_submit_guard.py"
    ),
    "review_chain_state_doctor.py": (
        "review_chain_doctor.py"
    ),
    "phase7_2_executor_enablement_review_packet.py": (
        "executor_enablement_review.py"
    ),
    "phase7_3_disabled_signed_testnet_executor_review.py": (
        "disabled_executor_review.py"
    ),
    "phase7_4_disabled_execution_reconciliation_session_close.py": (
        "disabled_session_reconciliation.py"
    ),
    "phase7_5_reconciliation_session_close_review_packet.py": (
        "session_close_review.py"
    ),
    "phase7_6_disabled_signed_testnet_session_operator_handoff.py": (
        "session_operator_handoff.py"
    ),
    "phase7_7_future_executor_review_prerequisite_design.py": (
        "executor_prerequisite.py"
    ),
    "phase7_8_future_executor_approval_packet_template.py": (
        "executor_approval_template.py"
    ),
    "phase7_9_future_executor_approval_intake_validator.py": (
        "executor_approval_intake.py"
    ),
    "phase7_10_future_executor_approval_review_packet.py": (
        "executor_approval_packet_review.py"
    ),
    "phase7_11_future_executor_enablement_design_review.py": (
        "enablement_design.py"
    ),
    "phase7_12_future_executor_enablement_guard_fixture.py": (
        "enablement_guard_fixtures.py"
    ),
    "phase7_13_future_executor_enablement_review_packet.py": (
        "enablement_review.py"
    ),
    "phase7_14_future_executor_operator_decision_packet.py": (
        "operator_decision_packet.py"
    ),
}

AGGREGATE_MODULES = (
    "executor_review.py",
    "session_review.py",
    "executor_approval.py",
    "stage_transition.py",
    "pre_executor_review.py",
)

COMMON_REQUIRED_FUNCTIONS = {
    "latest_dir",
    "storage_dir",
    "read_latest_json",
    "read_optional_json",
    "safe_text",
    "bool_value",
    "number_value",
    "positive_number_within",
    "positive_integer_within",
    "is_zero_number",
    "placeholder_value",
    "canonical_utc_value",
    "hex_fingerprint_valid",
    "artifact_hash",
    "artifact_summary",
    "unsafe_true_fields",
    "unsafe_flags_by_artifact",
    "forbidden_secret_fields",
    "review_only_permission_state",
    "persist_report",
}

SEMANTIC_IMPORTS = (
    (
        "from crypto_ai_system.governance.executor_review "
        "import run_executor_review_chain"
    ),
    (
        "from crypto_ai_system.governance.session_review "
        "import run_session_review_chain"
    ),
    (
        "from crypto_ai_system.governance.executor_approval "
        "import run_executor_approval_chain"
    ),
    (
        "from crypto_ai_system.governance.stage_transition "
        "import run_stage_transition_chain"
    ),
    (
        "from crypto_ai_system.governance.pre_executor_review "
        "import run_pre_executor_review_chain"
    ),
)

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


def _load_json(
    path: Path,
) -> dict:
    if not path.exists():
        return {}

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    return (
        dict(
            payload
        )
        if isinstance(
            payload,
            dict,
        )
        else {}
    )


def _top_level_functions(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(
            path
        ),
    )

    return {
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


def main() -> int:
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    blockers: list[str] = []

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

    steps = (
        governance
        / "phase7_steps"
    )

    common = (
        governance
        / "common.py"
    )

    if not common.exists():
        blockers.append(
            "PHASE7_COMMON_MODULE_MISSING"
        )

    else:
        functions = (
            _top_level_functions(
                common
            )
        )

        missing_common = sorted(
            COMMON_REQUIRED_FUNCTIONS
            - functions
        )

        for name in missing_common:
            blockers.append(
                "PHASE7_COMMON_UTILITY_MISSING:"
                + name
            )

    for module_name in (
        AGGREGATE_MODULES
    ):
        path = (
            governance
            / module_name
        )

        if not path.exists():
            blockers.append(
                "PHASE7_AGGREGATE_MODULE_MISSING:"
                + module_name
            )

            continue

        text = path.read_text(
            encoding="utf-8"
        )

        if (
            "crypto_ai_system.governance.common"
            not in text
        ):
            blockers.append(
                "PHASE7_COMMON_IMPORT_MISSING:"
                + module_name
            )

        if (
            "crypto_ai_system.validation.phase7"
            in text
            or (
                "crypto_ai_system.validation."
                "review_chain_state_doctor"
                in text
            )
        ):
            blockers.append(
                "PHASE7_ACTIVE_LEGACY_IMPORT_REMAINS:"
                + module_name
            )

    init_path = (
        steps
        / "__init__.py"
    )

    if not init_path.exists():
        blockers.append(
            "PHASE7_SEMANTIC_STEP_PACKAGE_MISSING"
        )

    for (
        legacy_name,
        semantic_name,
    ) in STEP_MAPPINGS.items():
        semantic_path = (
            steps
            / semantic_name
        )

        legacy_path = (
            validation
            / legacy_name
        )

        semantic_import = (
            "crypto_ai_system.governance.phase7_steps."
            + semantic_path.stem
        )

        if not semantic_path.exists():
            blockers.append(
                "PHASE7_SEMANTIC_STEP_MISSING:"
                + semantic_name
            )

        else:
            semantic_text = (
                semantic_path.read_text(
                    encoding="utf-8"
                )
            )

            if (
                "crypto_ai_system.validation.phase7"
                in semantic_text
                or (
                    "crypto_ai_system.validation."
                    "review_chain_state_doctor"
                    in semantic_text
                )
            ):
                blockers.append(
                    "PHASE7_SEMANTIC_STEP_LEGACY_IMPORT_REMAINS:"
                    + semantic_name
                )

        if not legacy_path.exists():
            blockers.append(
                "PHASE7_LEGACY_WRAPPER_MISSING:"
                + legacy_name
            )

            continue

        wrapper_text = (
            legacy_path.read_text(
                encoding="utf-8"
            )
        )

        meaningful_lines = [
            line
            for line in (
                wrapper_text.splitlines()
            )
            if line.strip()
        ]

        if (
            len(
                meaningful_lines
            )
            > 12
        ):
            blockers.append(
                "PHASE7_LEGACY_WRAPPER_TOO_LARGE:"
                + legacy_name
            )

        if (
            semantic_import
            not in wrapper_text
        ):
            blockers.append(
                "PHASE7_LEGACY_WRAPPER_TARGET_INVALID:"
                + legacy_name
            )

    full_cycle = (
        root
        / "run_full_cycle.py"
    )

    if not full_cycle.exists():
        blockers.append(
            "RUN_FULL_CYCLE_MISSING"
        )

    else:
        full_cycle_text = (
            full_cycle.read_text(
                encoding="utf-8"
            )
        )

        for marker in (
            SEMANTIC_IMPORTS
        ):
            if marker not in (
                full_cycle_text
            ):
                blockers.append(
                    "PHASE7_SEMANTIC_FULL_CYCLE_IMPORT_MISSING:"
                    + marker
                )

        if (
            "crypto_ai_system.validation.phase7"
            in full_cycle_text
        ):
            blockers.append(
                "PHASE7_DIRECT_FULL_CYCLE_IMPORT_REMAINS"
            )

    closure_path = (
        root
        / "config"
        / "lean"
        / "phase7_lean_closure.json"
    )

    closure = (
        _load_json(
            closure_path
        )
    )

    if (
        closure.get(
            "status"
        )
        != "PHASE7_LEAN_MERGE_CLOSED"
    ):
        blockers.append(
            "PHASE7_LEAN_CLOSURE_STATUS_INVALID"
        )

    if (
        closure.get(
            "runtime_authority"
        )
        is not False
    ):
        blockers.append(
            "PHASE7_LEAN_CLOSURE_RUNTIME_AUTHORITY_INVALID"
        )

    wrapper_policy = (
        closure.get(
            "legacy_wrapper_policy"
        )
        or {}
    )

    if (
        wrapper_policy.get(
            "historical_imports_preserved"
        )
        is not True
    ):
        blockers.append(
            "PHASE7_HISTORICAL_IMPORT_POLICY_INVALID"
        )

    if (
        wrapper_policy.get(
            "legacy_files_are_thin_wrappers"
        )
        is not True
    ):
        blockers.append(
            "PHASE7_THIN_WRAPPER_POLICY_INVALID"
        )

    if (
        wrapper_policy.get(
            "active_orchestration_uses_legacy_phase_imports"
        )
        is not False
    ):
        blockers.append(
            "PHASE7_ACTIVE_IMPORT_POLICY_INVALID"
        )

    safety = (
        closure.get(
            "safety"
        )
        or {}
    )

    for field in sorted(
        FORBIDDEN_TRUE
    ):
        if (
            safety.get(
                field
            )
            is not False
        ):
            blockers.append(
                "PHASE7_LEAN_CLOSURE_UNSAFE_FLAG:"
                + field
            )

    if (
        closure.get(
            "next_work"
        )
        != (
            "PHASE8_SIGNED_TESTNET_"
            "EXECUTION_PREPARATION"
        )
    ):
        blockers.append(
            "PHASE7_LEAN_CLOSURE_NEXT_WORK_INVALID"
        )

    migration = _load_json(
        root
        / "config"
        / "lean"
        / "lean_migration_state.json"
    )

    phase7_completed = (
        migration.get(
            "completed",
            {},
        ).get(
            "phase7_pre_executor",
            {},
        )
    )

    current = (
        migration.get(
            "current",
            {},
        )
    )

    if (
        phase7_completed.get(
            "status"
        )
        != "CLOSED"
    ):
        blockers.append(
            "PHASE7_MIGRATION_COMPLETED_STATE_MISSING"
        )

    if (
        current.get(
            "status"
        )
        not in {
            "PHASE7_LEAN_MERGE_CLOSED",
            (
                "PHASE8_M1_EXECUTION_PREPARATION_"
                "DESIGN_COMPLETE"
            ),
            (
                "PHASE8_FRESH_RUNTIME_EVIDENCE_AND_"
                "PHASE9_SINGLE_ORDER_REVIEW_IMPLEMENTED_REVIEW_ONLY"
            ),
        }
    ):
        blockers.append(
            "PHASE7_MIGRATION_STATE_NOT_CLOSED_OR_ADVANCED"
        )

    if (
        current.get(
            "next_step"
        )
        not in {
            (
                "PHASE8_SIGNED_TESTNET_"
                "EXECUTION_PREPARATION"
            ),
            (
                "PHASE8_M2_METADATA_KEY_SCOPE_"
                "AND_WRITE_PATH_DRY_VALIDATION"
            ),
            (
                "COLLECT_FRESH_PHASE8_RUNTIME_EVIDENCE_AND_"
                "COMPLETE_PHASE9_SINGLE_ORDER_REVIEW"
            ),
        }
    ):
        blockers.append(
            "PHASE7_MIGRATION_NEXT_STEP_INVALID"
        )

    if (
        migration.get(
            "execution_permissions_changed"
        )
        is not False
    ):
        blockers.append(
            "PHASE7_EXECUTION_PERMISSION_CHANGE_INVALID"
        )

    for relative in (
        "docs/architecture/PHASE7_LEAN_ARCHITECTURE.md",
        "docs/history/PHASE7_HISTORY_INDEX.md",
    ):
        if not (
            root
            / relative
        ).exists():
            blockers.append(
                "PHASE7_CLOSURE_DOCUMENT_MISSING:"
                + relative
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
        "PHASE7_LEAN_CLOSURE_VALID"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
