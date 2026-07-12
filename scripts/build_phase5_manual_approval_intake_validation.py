from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report


def main() -> None:
    report = persist_phase5_manual_approval_intake_validation_report()
    print(report.get("status"))
    print("manual_approval_submission_present=", report.get("manual_approval_submission_present"))
    print("approval_intake_status=", report.get("approval_intake_status"))
    print("approval_intake_validated=", report.get("approval_intake_validated"))
    print("signed_testnet_unlock_allowed=", report.get("signed_testnet_unlock_allowed"))


if __name__ == "__main__":
    main()
