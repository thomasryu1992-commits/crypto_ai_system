from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_9_future_executor_approval_intake_validator import (
    persist_phase7_9_future_executor_approval_intake_validator_report,
)


def main() -> None:
    report = persist_phase7_9_future_executor_approval_intake_validator_report()
    print(report.get("status"))
    print("phase7_9_intake_validation_ready=", report.get("phase7_9_intake_validation_ready"))
    print("future_executor_approval_intake_validation_record_created=", report.get("future_executor_approval_intake_validation_record_created"))
    print("intake_guard_passed=", report.get("intake_guard_passed"))
    print("valid_future_executor_approval_submission_passed_review_only_validation=", report.get("valid_future_executor_approval_submission_passed_review_only_validation"))
    print("invalid_future_executor_approval_submission_fixtures_blocked_fail_closed=", report.get("invalid_future_executor_approval_submission_fixtures_blocked_fail_closed"))
    print("actual_executor_approval_created=", report.get("actual_executor_approval_created"))
    print("actual_executor_enablement_performed=", report.get("actual_executor_enablement_performed"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("external_order_submission_performed=", report.get("external_order_submission_performed"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
