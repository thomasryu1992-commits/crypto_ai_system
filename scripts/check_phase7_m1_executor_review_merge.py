from __future__ import annotations

import json
from pathlib import Path


DIRECT_IMPORTS = (
    "crypto_ai_system.validation."
    "phase7_signed_testnet_validation_design_guard",
    "crypto_ai_system.validation."
    "phase7_1_signed_testnet_pre_submit_payload_guard",
    "crypto_ai_system.validation."
    "review_chain_state_doctor",
    "crypto_ai_system.validation."
    "phase7_2_executor_enablement_review_packet",
    "crypto_ai_system.validation."
    "phase7_3_disabled_signed_testnet_executor_review",
)

FORBIDDEN_TRUE = {
    "runtime_permission_source",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_executor_enablement_authority",
    "signed_testnet_order_submission_authority",
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
    root = Path(__file__).resolve().parents[1]
    blockers: list[str] = []

    module = (
        root
        / "src"
        / "crypto_ai_system"
        / "governance"
        / "executor_review.py"
    )

    if not module.exists():
        blockers.append(
            "PHASE7_M1_EXECUTOR_REVIEW_MODULE_MISSING"
        )
    else:
        text = module.read_text(encoding="utf-8")

        for required in (
            "run_executor_review_chain",
            "build_executor_review_report",
            "DISABLED_EXECUTOR_REVIEW_ONLY",
            "REVIEW_CHAIN_REPAIR_REQUIRED",
            "BLOCKED",
        ):
            if required not in text:
                blockers.append(
                    "PHASE7_M1_EXECUTOR_REVIEW_CONTRACT_MISSING:"
                    + required
                )

    full_cycle = (
        root / "run_full_cycle.py"
    ).read_text(encoding="utf-8")

    expected_import = (
        "from crypto_ai_system.governance.executor_review "
        "import run_executor_review_chain"
    )

    if expected_import not in full_cycle:
        blockers.append(
            "PHASE7_M1_FULL_CYCLE_EXECUTOR_REVIEW_IMPORT_MISSING"
        )

    for direct in DIRECT_IMPORTS:
        if direct in full_cycle:
            blockers.append(
                "PHASE7_M1_FULL_CYCLE_DIRECT_IMPORT_REMAINS:"
                + direct
            )

    if '"executor_review": executor_review' not in full_cycle:
        blockers.append(
            "PHASE7_M1_FULL_CYCLE_EXECUTOR_REVIEW_OUTPUT_MISSING"
        )

    milestone_path = (
        root
        / "config"
        / "lean"
        / "phase7_m1_executor_review.json"
    )

    if not milestone_path.exists():
        blockers.append(
            "PHASE7_M1_MILESTONE_MANIFEST_MISSING"
        )
    else:
        payload = json.loads(
            milestone_path.read_text(encoding="utf-8")
        )

        if (
            payload.get("status")
            != "PHASE7_M1_EXECUTOR_REVIEW_MERGED"
        ):
            blockers.append(
                "PHASE7_M1_MILESTONE_STATUS_INVALID"
            )

        if payload.get("runtime_authority") is not False:
            blockers.append(
                "PHASE7_M1_RUNTIME_AUTHORITY_MUST_BE_FALSE"
            )

        safety = payload.get("safety") or {}

        for flag in sorted(FORBIDDEN_TRUE):
            if safety.get(flag) is not False:
                blockers.append(
                    f"PHASE7_M1_UNSAFE_MILESTONE_FLAG:{flag}"
                )

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)

        return 2

    print("PHASE7_M1_EXECUTOR_REVIEW_MERGE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
