from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_12_future_executor_enablement_guard_fixture import (
    persist_phase7_12_future_executor_enablement_guard_fixture_report,
)


def main() -> None:
    report = persist_phase7_12_future_executor_enablement_guard_fixture_report()
    print(report.get("status"))
    print("phase7_12_guard_fixture_ready=", report.get("phase7_12_guard_fixture_ready"))
    print("valid_enablement_guard_fixture_created=", report.get("valid_enablement_guard_fixture_created"))
    print("valid_enablement_guard_fixture_passed_review_only_validation=", report.get("valid_enablement_guard_fixture_passed_review_only_validation"))
    print("invalid_enablement_guard_fixtures_blocked_fail_closed=", report.get("invalid_enablement_guard_fixtures_blocked_fail_closed"))
    print("enablement_guard_fixture_guard_passed=", report.get("enablement_guard_fixture_guard_passed"))
    print("actual_executor_enablement_performed=", report.get("actual_executor_enablement_performed"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
