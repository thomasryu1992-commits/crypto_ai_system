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
            "PHASE8_M1_EXECUTION_PREPARATION_"
            "DESIGN_COMPLETE"
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

    for (
        field,
        value,
    ) in (
        runtime_validation.items()
    ):
        if value is not False:
            blockers.append(
                "PHASE8_M1_RUNTIME_VALIDATION_MUST_REMAIN_FALSE:"
                + str(
                    field
                )
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
            "PHASE8_M2_METADATA_KEY_SCOPE_"
            "AND_WRITE_PATH_DRY_VALIDATION"
        )
    ):
        blockers.append(
            "PHASE8_M1_NEXT_WORK_INVALID"
        )

    migration = _load_json(
        root
        / "config"
        / "lean"
        / "lean_migration_state.json"
    )

    if (
        migration.get(
            "current",
            {},
        ).get(
            "status"
        )
        != (
            "PHASE8_M1_EXECUTION_PREPARATION_"
            "DESIGN_COMPLETE"
        )
    ):
        blockers.append(
            "PHASE8_M1_MIGRATION_STATUS_INVALID"
        )

    if (
        migration.get(
            "current",
            {},
        ).get(
            "next_step"
        )
        != (
            "PHASE8_M2_METADATA_KEY_SCOPE_"
            "AND_WRITE_PATH_DRY_VALIDATION"
        )
    ):
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
