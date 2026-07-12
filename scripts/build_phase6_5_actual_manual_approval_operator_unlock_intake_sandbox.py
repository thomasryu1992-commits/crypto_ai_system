from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase6_5_actual_manual_approval_operator_unlock_intake_sandbox import persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report


def main() -> None:
    report = persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report()
    print(report.get("status"))
    print("actual_manual_approval_submission_present=", report.get("actual_manual_approval_submission_present"))
    print("actual_operator_unlock_request_present=", report.get("actual_operator_unlock_request_present"))
    print("phase7_entry_review_possible=", report.get("phase7_entry_review_possible"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
