from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

# Historical command compatibility. Active implementation is semantic.
from crypto_ai_system.governance.operator_handoff import (
    persist_phase5_1_manual_approval_operator_handoff_report,
)


def main() -> None:
    report = persist_phase5_1_manual_approval_operator_handoff_report()
    print(report.get("status"))
    print(
        "manual_approval_submission_template_created=",
        report.get("manual_approval_submission_template_created"),
    )
    print(
        "manual_approval_submission_created=",
        report.get("manual_approval_submission_created"),
    )
    print(
        "approval_intake_submitted=",
        report.get("approval_intake_submitted"),
    )
    print(
        "signed_testnet_unlock_allowed=",
        report.get("signed_testnet_unlock_allowed"),
    )


if __name__ == "__main__":
    main()
