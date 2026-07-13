from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.operator_unlock_fixtures import persist_phase6_2_operator_unlock_request_fixture_validator_report


def main() -> None:
    report = persist_phase6_2_operator_unlock_request_fixture_validator_report()
    print(report.get("status"))
    print("valid_operator_unlock_fixture_passed_review_only_validation=", report.get("valid_operator_unlock_fixture_passed_review_only_validation"))
    print("invalid_operator_unlock_fixtures_blocked_fail_closed=", report.get("invalid_operator_unlock_fixtures_blocked_fail_closed"))
    print("operator_unlock_request_created=", report.get("operator_unlock_request_created"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
