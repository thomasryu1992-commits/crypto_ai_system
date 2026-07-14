from __future__ import annotations

import json
from pathlib import Path


DIRECT_IMPORTS = (
    "crypto_ai_system.validation."
    "phase7_7_future_executor_review_prerequisite_design",
    "crypto_ai_system.validation."
    "phase7_8_future_executor_approval_packet_template",
    "crypto_ai_system.validation."
    "phase7_9_future_executor_approval_intake_validator",
    "crypto_ai_system.validation."
    "phase7_10_future_executor_approval_review_packet",
)

FORBIDDEN_TRUE = {
    "runtime_permission_source",
    "executor_approval_runtime_authority",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_executor_approval_authority",
    "signed_testnet_execution_authority",
    "signed_testnet_order_submission_authority",
    "signed_testnet_promotion_authority",
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
        / "executor_approval.py"
    )

    if not module.exists():
        blockers.append(
            "PHASE7_M3_EXECUTOR_APPROVAL_MODULE_MISSING"
        )

    else:
        text = module.read_text(
            encoding="utf-8"
        )

        for required in (
            "run_executor_approval_chain",
            "build_executor_approval_report",
            "FUTURE_EXECUTOR_APPROVAL_FIXTURE_REVIEW_ONLY",
            "OPERATOR_SUBMISSION_VALIDATED_REVIEW_ONLY",
            "APPROVAL_EVIDENCE_REPAIR_REQUIRED",
            "BLOCKED",
            "fixture_validation_is_executor_approval",
            "operator_submission_validation_is_runtime_authority",
        ):
            if required not in text:
                blockers.append(
                    "PHASE7_M3_EXECUTOR_APPROVAL_CONTRACT_MISSING:"
                    + required
                )

    full_cycle = (
        root
        / "run_full_cycle.py"
    ).read_text(
        encoding="utf-8"
    )

    expected_import = (
        "from crypto_ai_system.governance.executor_approval "
        "import run_executor_approval_chain"
    )

    if expected_import not in full_cycle:
        blockers.append(
            "PHASE7_M3_FULL_CYCLE_EXECUTOR_APPROVAL_IMPORT_MISSING"
        )

    for direct in DIRECT_IMPORTS:
        if direct in full_cycle:
            blockers.append(
                "PHASE7_M3_FULL_CYCLE_DIRECT_IMPORT_REMAINS:"
                + direct
            )

    if (
        '"executor_approval_review": '
        "executor_approval_review"
        not in full_cycle
    ):
        blockers.append(
            "PHASE7_M3_FULL_CYCLE_EXECUTOR_APPROVAL_OUTPUT_MISSING"
        )

    milestone_path = (
        root
        / "config"
        / "lean"
        / "phase7_m3_executor_approval.json"
    )

    if not milestone_path.exists():
        blockers.append(
            "PHASE7_M3_MILESTONE_MANIFEST_MISSING"
        )

    else:
        payload = json.loads(
            milestone_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            payload.get("status")
            != "PHASE7_M3_EXECUTOR_APPROVAL_MERGED"
        ):
            blockers.append(
                "PHASE7_M3_MILESTONE_STATUS_INVALID"
            )

        if (
            payload.get(
                "runtime_authority"
            )
            is not False
        ):
            blockers.append(
                "PHASE7_M3_RUNTIME_AUTHORITY_MUST_BE_FALSE"
            )

        fixture_policy = (
            payload.get(
                "fixture_policy"
            )
            or {}
        )

        for field in (
            "fixture_validation_is_executor_approval",
            "fixture_validation_is_runtime_authority",
            "fixture_validation_can_unlock_signed_testnet",
            "fixture_validation_can_unlock_live",
        ):
            if (
                fixture_policy.get(
                    field
                )
                is not False
            ):
                blockers.append(
                    "PHASE7_M3_FIXTURE_POLICY_INVALID:"
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
                    "PHASE7_M3_UNSAFE_MILESTONE_FLAG:"
                    + flag
                )

    if blockers:
        for blocker in sorted(
            set(blockers)
        ):
            print(
                blocker
            )

        return 2

    print(
        "PHASE7_M3_EXECUTOR_APPROVAL_MERGE_VALID"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
