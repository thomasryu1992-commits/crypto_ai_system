from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import persist_phase5_2_manual_approval_submission_fixture_validator_report


def main() -> None:
    report = persist_phase5_2_manual_approval_submission_fixture_validator_report()
    print(report.get("status"))
    print("valid_fixture_passed_review_only_validation=", report.get("valid_fixture_passed_review_only_validation"))
    print("invalid_fixtures_blocked_fail_closed=", report.get("invalid_fixtures_blocked_fail_closed"))
    print("manual_approval_submission_created=", report.get("manual_approval_submission_created"))
    print("signed_testnet_unlock_allowed=", report.get("signed_testnet_unlock_allowed"))


if __name__ == "__main__":
    main()
