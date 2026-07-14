from __future__ import annotations

import json
from pathlib import Path


DIRECT_IMPORTS = (
    "crypto_ai_system.validation."
    "phase7_11_future_executor_enablement_design_review",
    "crypto_ai_system.validation."
    "phase7_12_future_executor_enablement_guard_fixture",
    "crypto_ai_system.validation."
    "phase7_13_future_executor_enablement_review_packet",
    "crypto_ai_system.validation."
    "phase7_14_future_executor_operator_decision_packet",
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
    "actual_operator_decision_recorded",
    "actual_stage_transition_performed",
    "actual_executor_approval_created",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "actual_cancel_performed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
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
        / "stage_transition.py"
    )

    if not module.exists():
        blockers.append(
            "PHASE7_M4_STAGE_TRANSITION_MODULE_MISSING"
        )

    else:
        text = module.read_text(
            encoding="utf-8"
        )

        for required in (
            "run_stage_transition_chain",
            "build_stage_transition_review_report",
            "OPERATOR_DECISION_PACKET_REVIEW_ONLY",
            "STAGE_TRANSITION_EVIDENCE_REPAIR_REQUIRED",
            "BLOCKED",
            "operator_decision_packet_is_operator_decision",
            "operator_decision_packet_is_runtime_authority",
            "operator_decision_packet_can_transition_stage",
        ):
            if required not in text:
                blockers.append(
                    "PHASE7_M4_STAGE_TRANSITION_CONTRACT_MISSING:"
                    + required
                )

    full_cycle = (
        root
        / "run_full_cycle.py"
    ).read_text(
        encoding="utf-8"
    )

    expected_import = (
        "from crypto_ai_system.governance.stage_transition "
        "import run_stage_transition_chain"
    )

    if expected_import not in full_cycle:
        blockers.append(
            "PHASE7_M4_FULL_CYCLE_STAGE_TRANSITION_IMPORT_MISSING"
        )

    for direct in DIRECT_IMPORTS:
        if direct in full_cycle:
            blockers.append(
                "PHASE7_M4_FULL_CYCLE_DIRECT_IMPORT_REMAINS:"
                + direct
            )

    if (
        '"stage_transition_review": '
        "stage_transition_review"
        not in full_cycle
    ):
        blockers.append(
            "PHASE7_M4_FULL_CYCLE_STAGE_TRANSITION_OUTPUT_MISSING"
        )

    milestone_path = (
        root
        / "config"
        / "lean"
        / "phase7_m4_stage_transition.json"
    )

    if not milestone_path.exists():
        blockers.append(
            "PHASE7_M4_MILESTONE_MANIFEST_MISSING"
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
            != "PHASE7_M4_STAGE_TRANSITION_MERGED"
        ):
            blockers.append(
                "PHASE7_M4_MILESTONE_STATUS_INVALID"
            )

        if (
            payload.get(
                "runtime_authority"
            )
            is not False
        ):
            blockers.append(
                "PHASE7_M4_RUNTIME_AUTHORITY_MUST_BE_FALSE"
            )

        policy = (
            payload.get(
                "operator_decision_packet_policy"
            )
            or {}
        )

        for field in (
            "operator_decision_packet_is_operator_decision",
            "operator_decision_packet_is_runtime_authority",
            "operator_decision_packet_can_enable_executor",
            "operator_decision_packet_can_submit_order",
            "operator_decision_packet_can_transition_stage",
        ):
            if (
                policy.get(
                    field
                )
                is not False
            ):
                blockers.append(
                    "PHASE7_M4_OPERATOR_DECISION_PACKET_POLICY_INVALID:"
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
                    "PHASE7_M4_UNSAFE_MILESTONE_FLAG:"
                    + flag
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
        "PHASE7_M4_STAGE_TRANSITION_MERGE_VALID"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
