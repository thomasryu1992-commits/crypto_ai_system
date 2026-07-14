from __future__ import annotations

import ast
import json
from pathlib import Path


FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websocket",
    "websockets",
}

FORBIDDEN_TRUE = {
    "runtime_permission_source",
    "operator_decision_runtime_authority",
    "stage_transition_authority",
    "executor_enablement_authority",
    "executor_approval_authority",
    "signed_testnet_unlock_authority",
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
    "adapter_write_routing_enabled",
    "request_signing_allowed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
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
        dict(payload)
        if isinstance(
            payload,
            dict,
        )
        else {}
    )


def main() -> int:
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    blockers: list[str] = []

    module_path = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "signed_testnet_execution_preparation.py"
    )

    if not module_path.exists():
        blockers.append(
            "PHASE8_M1_MODULE_MISSING"
        )

    else:
        text = module_path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            text,
            filename=str(
                module_path
            ),
        )

        functions = {
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

        required_functions = {
            "build_secret_handling_design",
            "build_write_path_dry_validation_contract",
            "validate_metadata_only_key_scope",
            "validate_write_path_dry",
            "validate_hot_path_pre_order_risk_gate",
            "_build_phase8_review_only_artifact",
            "validate_executor_final_guard",
            "build_hot_path_risk_gate_contract",
            "build_executor_final_guard_design",
            "build_signed_testnet_execution_preparation_report",
            "run_signed_testnet_execution_preparation_chain",
            "run_signed_testnet_execution_preparation_latest",
        }

        for name in sorted(
            required_functions
            - functions
        ):
            blockers.append(
                "PHASE8_M1_REQUIRED_FUNCTION_MISSING:"
                + name
            )

        for node in ast.walk(
            tree
        ):
            if isinstance(
                node,
                ast.Import,
            ):
                for alias in node.names:
                    root_name = (
                        alias.name.split(
                            "."
                        )[0]
                    )

                    if (
                        root_name
                        in FORBIDDEN_IMPORT_ROOTS
                    ):
                        blockers.append(
                            "PHASE8_M1_NETWORK_LIBRARY_IMPORT_FORBIDDEN:"
                            + alias.name
                        )

            if isinstance(
                node,
                ast.ImportFrom,
            ):
                root_name = (
                    str(
                        node.module
                        or ""
                    )
                    .split(
                        "."
                    )[0]
                )

                if (
                    root_name
                    in FORBIDDEN_IMPORT_ROOTS
                ):
                    blockers.append(
                        "PHASE8_M1_NETWORK_LIBRARY_IMPORT_FORBIDDEN:"
                        + str(
                            node.module
                        )
                    )

        for forbidden_literal in (
            "subprocess.run(",
            "os.system(",
            "socket.socket(",
            "create_connection(",
            "sendall(",
        ):
            if (
                forbidden_literal
                in text
            ):
                blockers.append(
                    "PHASE8_M1_RUNTIME_IO_CALL_FORBIDDEN:"
                    + forbidden_literal
                )

        for required_literal in (
            "metadata_only_required",
            "secret_dereference_allowed",
            "exchange_write_endpoint_invocation_enabled",
            "phase8_m2_validators_implemented_in_place",
            "phase8_m2_new_runtime_module_created",
            "phase8_m2_validation_complete",
            "metadata_only_key_scope_validation",
            "write_path_dry_validation",
            "network_transport_invocation_count",
            "request_signing_invocation_count",
            "exchange_endpoint_call_count",
            "place_order_method_called",
            "cancel_order_method_called",
            "phase8_m3_validator_implemented_in_place",
            "phase8_m3_new_runtime_module_created",
            "phase8_m3_validation_complete",
            "hot_path_pre_order_risk_gate_validation",
            "must_run_immediately_before_executor",
            "must_run_after_final_order_payload_is_frozen",
            "freshness_budget_seconds",
            "cold_path_risk_result_reused",
            "phase8_m4_validator_implemented_in_place",
            "phase8_m4_new_runtime_module_created",
            "phase8_m4_validation_complete",
            "executor_final_guard_validation",
            "aggregates_existing_m2_m3_results",
            "duplicates_m2_m3_checks",
            "must_run_after_hot_path_risk_gate",
            "must_run_before_any_executor_enablement",
            "phase9_separate_approval_required",
            "phase9_order_submission_permission_granted",
            "phase8_implementation_complete",
            "phase8_architecture_compressed_in_place",
            "phase8_contract_artifact_schema_preserved",
            "phase8_single_active_module",
            "phase8_new_runtime_modules_created",
            "phase8_integrated_runtime_validation_complete",
            "phase8_completion_review_state",
            "phase9_approval_review_allowed",
            "must_run_immediately_before_executor",
            "executor_final_guard_runtime_implemented",
            "phase8_execution_preparation_ready",
            "phase8_execution_allowed",
            "phase8_order_submission_allowed",
            "request_signing_allowed",
            "exchange_endpoint_called",
        ):
            if (
                required_literal
                not in text
            ):
                blockers.append(
                    "PHASE8_M1_BOUNDARY_CONTRACT_MISSING:"
                    + required_literal
                )

    module_text = (
        module_path.read_text(encoding="utf-8")
        if module_path.exists()
        else ""
    )
    m2_assignment_index = module_text.find(
        "phase8_m2_validation_complete = ("
    )
    m2_reference_index = module_text.find(
        "if not phase8_m2_validation_complete"
    )
    if (
        m2_reference_index != -1
        and (
            m2_assignment_index == -1
            or m2_reference_index < m2_assignment_index
        )
    ):
        blockers.append(
            "PHASE8_M2_COMPLETION_REFERENCED_BEFORE_ASSIGNMENT"
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
            "from crypto_ai_system.governance."
            "signed_testnet_execution_preparation "
            "import run_signed_testnet_execution_preparation_chain"
        )

        if (
            expected_import
            not in full_cycle
        ):
            blockers.append(
                "PHASE8_M1_FULL_CYCLE_IMPORT_MISSING"
            )

        if (
            '"signed_testnet_execution_preparation": '
            "signed_testnet_execution_preparation"
            not in full_cycle
        ):
            blockers.append(
                "PHASE8_M1_FULL_CYCLE_OUTPUT_MISSING"
            )

    phase7_closure = _load_json(
        root
        / "config"
        / "lean"
        / "phase7_lean_closure.json"
    )

    if (
        phase7_closure.get(
            "status"
        )
        != "PHASE7_LEAN_MERGE_CLOSED"
    ):
        blockers.append(
            "PHASE8_M1_PHASE7_CLOSURE_NOT_READY"
        )

    milestone = _load_json(
        root
        / "config"
        / "lean"
        / "phase8_m1_execution_preparation.json"
    )

    if (
        milestone.get(
            "status"
        )
        != (
            "PHASE8_FRESH_RUNTIME_EVIDENCE_AND_"
            "PHASE9_SINGLE_ORDER_REVIEW_IMPLEMENTED_REVIEW_ONLY"
        )
    ):
        blockers.append(
            "PHASE8_M1_MILESTONE_STATUS_INVALID"
        )

    if (
        milestone.get(
            "runtime_authority"
        )
        is not False
    ):
        blockers.append(
            "PHASE8_M1_RUNTIME_AUTHORITY_INVALID"
        )

    design_completion = (
        milestone.get(
            "design_completion"
        )
        or {}
    )

    for field in (
        "secret_handling_design_complete",
        "write_path_dry_validation_contract_complete",
        "hot_path_risk_gate_contract_complete",
        "executor_final_guard_design_complete",
    ):
        if (
            design_completion.get(
                field
            )
            is not True
        ):
            blockers.append(
                "PHASE8_M1_DESIGN_INCOMPLETE:"
                + field
            )

    runtime_validation = (
        milestone.get(
            "runtime_validation"
        )
        or {}
    )

    expected_runtime_validation = {
        "hot_path_risk_gate_runtime_implemented": True,
        "executor_final_guard_runtime_implemented": True,
    }

    for (
        field,
        value,
    ) in (
        runtime_validation.items()
    ):
        expected = expected_runtime_validation.get(field, False)
        if value is not expected:
            blockers.append(
                "PHASE8_RUNTIME_VALIDATION_STATE_INVALID:"
                + str(field)
            )

    phase8_boundary = (
        milestone.get(
            "phase8_boundary"
        )
        or {}
    )

    for field in (
        "secret_value_handling_allowed",
        "request_signing_allowed",
        "network_write_transport_allowed",
        "exchange_order_endpoint_call_allowed",
        "executor_enablement_allowed",
        "testnet_order_submission_allowed",
        "stage_transition_allowed",
    ):
        if (
            phase8_boundary.get(
                field
            )
            is not False
        ):
            blockers.append(
                "PHASE8_M1_BOUNDARY_FLAG_INVALID:"
                + field
            )

    safety = (
        milestone.get(
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
                "PHASE8_M1_UNSAFE_FLAG:"
                + field
            )

    if (
        milestone.get(
            "next_work"
        )
        != (
            "COLLECT_FRESH_PHASE8_RUNTIME_EVIDENCE_AND_"
            "COMPLETE_PHASE9_SINGLE_ORDER_REVIEW"
        )
    ):
        blockers.append(
            "PHASE8_M1_NEXT_WORK_INVALID"
        )

    in_place_m2 = (
        milestone.get("in_place_m2")
        or {}
    )

    for field in (
        "metadata_only_key_scope_validator_implemented",
        "write_path_dry_validator_implemented",
        "uses_existing_active_module",
        "uses_existing_test_file",
        "uses_existing_checker",
        "uses_existing_manifest",
    ):
        if in_place_m2.get(field) is not True:
            blockers.append(
                "PHASE8_M2_IN_PLACE_POLICY_INVALID:"
                + field
            )

    for field in (
        "new_runtime_module_created",
        "new_test_file_created",
        "new_checker_created",
        "new_manifest_created",
        "execution_permissions_changed",
    ):
        if in_place_m2.get(field) is not False:
            blockers.append(
                "PHASE8_M2_FILE_GROWTH_OR_PERMISSION_INVALID:"
                + field
            )

    in_place_m3 = (
        milestone.get("in_place_m3")
        or {}
    )

    for field in (
        "hot_path_pre_order_risk_gate_validator_implemented",
        "uses_existing_active_module",
        "uses_existing_test_file",
        "uses_existing_checker",
        "uses_existing_manifest",
        "m2_evaluation_order_fixed",
    ):
        if in_place_m3.get(field) is not True:
            blockers.append(
                "PHASE8_M3_IN_PLACE_POLICY_INVALID:" + field
            )

    for field in (
        "new_runtime_module_created",
        "new_test_file_created",
        "new_checker_created",
        "new_manifest_created",
        "execution_permissions_changed",
    ):
        if in_place_m3.get(field) is not False:
            blockers.append(
                "PHASE8_M3_FILE_GROWTH_OR_PERMISSION_INVALID:" + field
            )

    in_place_m4 = (
        milestone.get("in_place_m4")
        or {}
    )

    for field in (
        "executor_final_guard_validator_implemented",
        "aggregates_existing_m2_m3_results",
        "uses_existing_active_module",
        "uses_existing_test_file",
        "uses_existing_checker",
        "uses_existing_manifest",
    ):
        if in_place_m4.get(field) is not True:
            blockers.append(
                "PHASE8_M4_IN_PLACE_POLICY_INVALID:" + field
            )

    if in_place_m4.get("duplicates_m2_m3_checks") is not False:
        blockers.append(
            "PHASE8_M4_IN_PLACE_POLICY_INVALID:duplicates_m2_m3_checks"
        )

    for field in (
        "new_runtime_module_created",
        "new_test_file_created",
        "new_checker_created",
        "new_manifest_created",
        "execution_permissions_changed",
    ):
        if in_place_m4.get(field) is not False:
            blockers.append(
                "PHASE8_M4_FILE_GROWTH_OR_PERMISSION_INVALID:" + field
            )

    integrated_review = (
        milestone.get("integrated_completion_review")
        or {}
    )

    for field in (
        "implementation_complete",
        "single_active_module",
        "contract_builders_share_factory",
        "artifact_schema_preserved",
        "uses_existing_test_file",
        "uses_existing_checker",
        "uses_existing_manifest",
    ):
        if integrated_review.get(field) is not True:
            blockers.append(
                "PHASE8_INTEGRATED_REVIEW_POLICY_INVALID:"
                + field
            )

    for field in (
        "new_runtime_module_created",
        "new_test_file_created",
        "new_checker_created",
        "new_manifest_created",
        "execution_permissions_changed",
    ):
        if integrated_review.get(field) is not False:
            blockers.append(
                "PHASE8_INTEGRATED_REVIEW_GROWTH_OR_PERMISSION_INVALID:"
                + field
            )

    if (
        integrated_review.get("runtime_validation_complete")
        is not False
    ):
        blockers.append(
            "PHASE8_DEFAULT_RUNTIME_VALIDATION_MUST_REMAIN_PENDING"
        )

    module_source = (
        module_path.read_text(encoding="utf-8")
        if module_path.exists()
        else ""
    )

    module_tree = (
        ast.parse(module_source)
        if module_source
        else None
    )

    if module_tree is not None:
        builders = {
            node.name: node
            for node in module_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {
                "build_secret_handling_design",
                "build_write_path_dry_validation_contract",
                "build_hot_path_risk_gate_contract",
                "build_executor_final_guard_design",
            }
        }

        total_builder_lines = sum(
            int(node.end_lineno or node.lineno)
            - int(node.lineno)
            + 1
            for node in builders.values()
        )

        if len(builders) != 4:
            blockers.append(
                "PHASE8_COMPRESSED_CONTRACT_BUILDERS_MISSING"
            )

        if total_builder_lines > 210:
            blockers.append(
                "PHASE8_CONTRACT_BUILDERS_NOT_COMPRESSED:"
                + str(total_builder_lines)
            )

        for name, node in builders.items():
            segment = (
                ast.get_source_segment(
                    module_source,
                    node,
                )
                or ""
            )

            if (
                "_build_phase8_review_only_artifact("
                not in segment
            ):
                blockers.append(
                    "PHASE8_BUILDER_NOT_USING_SHARED_FACTORY:"
                    + name
                )

            if (
                "stable_id("
                in segment
                or "sha256_json("
                in segment
            ):
                blockers.append(
                    "PHASE8_BUILDER_REPEATS_ID_HASH_BOILERPLATE:"
                    + name
                )

    phase8_phase9_review = (
        milestone.get(
            "fresh_runtime_evidence_phase9_review"
        )
        or {}
    )

    for field in (
        "phase8_fresh_runtime_evidence_projection_implemented",
        "uses_existing_phase8_report",
        "phase9_builder_uses_existing_executor_approval_module",
        "uses_existing_test_file",
        "uses_existing_checker",
        "uses_existing_manifest",
        "runtime_review_artifact_generation_allowed",
    ):
        if phase8_phase9_review.get(field) is not True:
            blockers.append(
                "PHASE8_PHASE9_REVIEW_POLICY_INVALID:"
                + field
            )

    for field in (
        "new_runtime_module_created",
        "new_test_file_created",
        "new_checker_created",
        "new_manifest_created",
        "actual_phase9_approval_created",
        "phase9_order_submission_permission_granted",
        "execution_permissions_changed",
    ):
        if phase8_phase9_review.get(field) is not False:
            blockers.append(
                "PHASE8_PHASE9_REVIEW_GROWTH_OR_PERMISSION_INVALID:"
                + field
            )

    if (
        phase8_phase9_review.get("maximum_order_count")
        != 1
    ):
        blockers.append(
            "PHASE9_REVIEW_MAXIMUM_ORDER_COUNT_INVALID"
        )

    phase8_source = (
        module_path.read_text(encoding="utf-8")
        if module_path.exists()
        else ""
    )

    executor_approval_path = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "executor_approval.py"
    )

    executor_approval_source = (
        executor_approval_path.read_text(
            encoding="utf-8"
        )
        if executor_approval_path.exists()
        else ""
    )

    required_phase8_literals = (
        "phase8_fresh_runtime_evidence_validated",
        "phase8_runtime_evidence_validation_id",
        "phase8_runtime_evidence_sources",
        "phase8_runtime_evidence_valid_for_phase9_review_only",
        "phase8_runtime_evidence_is_phase9_approval",
        "phase9_single_order_approval_review_packet",
    )

    for literal in required_phase8_literals:
        if literal not in phase8_source:
            blockers.append(
                "PHASE8_FRESH_EVIDENCE_CONTRACT_MISSING:"
                + literal
            )

    required_phase9_literals = (
        "def build_phase9_single_order_approval_review_packet(",
        '"approval_scope": "single_signed_testnet_order"',
        '"single_order_only": True',
        '"maximum_order_count": 1',
        '"explicit_operator_approval_required": True',
        '"actual_phase9_approval_created": False',
        '"phase9_approval_runtime_authority": False',
        '"phase9_executor_enablement_allowed": False',
        '"phase9_request_signing_allowed": False',
        '"phase9_order_submission_permission_granted": False',
        '"phase9_order_submission_performed": False',
        '"ready_for_signed_testnet_execution": False',
        '"testnet_order_submission_allowed": False',
        '"external_order_submission_performed": False',
    )

    for literal in required_phase9_literals:
        if literal not in executor_approval_source:
            blockers.append(
                "PHASE9_SINGLE_ORDER_REVIEW_CONTRACT_MISSING:"
                + literal
            )

    if (
        ".place_order("
        in executor_approval_source
        or ".cancel_order("
        in executor_approval_source
    ):
        blockers.append(
            "PHASE9_REVIEW_PACKET_MUST_NOT_CALL_EXECUTOR_METHODS"
        )

    migration = _load_json(
        root
        / "config"
        / "lean"
        / "lean_migration_state.json"
    )

    if migration.get("current", {}).get("status") not in {
        "PHASE8_M1_EXECUTION_PREPARATION_DESIGN_COMPLETE",
        (
            "PHASE8_FRESH_RUNTIME_EVIDENCE_AND_"
            "PHASE9_SINGLE_ORDER_REVIEW_IMPLEMENTED_REVIEW_ONLY"
        ),
    }:
        blockers.append(
            "PHASE8_M1_MIGRATION_STATUS_INVALID"
        )

    if migration.get("current", {}).get("next_step") not in {
        "PHASE8_M2_METADATA_KEY_SCOPE_AND_WRITE_PATH_DRY_VALIDATION",
        (
            "COLLECT_FRESH_PHASE8_RUNTIME_EVIDENCE_AND_"
            "COMPLETE_PHASE9_SINGLE_ORDER_REVIEW"
        ),
    }:
        blockers.append(
            "PHASE8_M1_MIGRATION_NEXT_STEP_INVALID"
        )

    if (
        migration.get(
            "execution_permissions_changed"
        )
        is not False
    ):
        blockers.append(
            "PHASE8_M1_EXECUTION_PERMISSION_CHANGE_INVALID"
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
        "PHASE8_M1_EXECUTION_PREPARATION_VALID"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
