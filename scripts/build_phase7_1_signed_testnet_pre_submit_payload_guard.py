from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_1_signed_testnet_pre_submit_payload_guard import persist_phase7_1_signed_testnet_pre_submit_payload_guard_report


def main() -> None:
    report = persist_phase7_1_signed_testnet_pre_submit_payload_guard_report()
    print(report.get("status"))
    print("phase7_1_payload_guard_ready_review_only=", report.get("phase7_1_payload_guard_ready_review_only"))
    print("valid_would_submit_payload_passed_review_only_validation=", report.get("valid_would_submit_payload_passed_review_only_validation"))
    print("invalid_payload_fixtures_blocked_fail_closed=", report.get("invalid_payload_fixtures_blocked_fail_closed"))
    print("phase7_execution_authority=", report.get("phase7_execution_authority"))
    print("phase7_order_submission_authority=", report.get("phase7_order_submission_authority"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
