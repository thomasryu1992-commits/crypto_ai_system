from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.readiness_gate import persist_phase6_3_signed_testnet_readiness_gate_review_report


def main() -> None:
    report = persist_phase6_3_signed_testnet_readiness_gate_review_report()
    print(report.get("status"))
    print("actual_manual_approval_submission_present=", report.get("actual_manual_approval_submission_present"))
    print("actual_operator_unlock_request_present=", report.get("actual_operator_unlock_request_present"))
    print("signed_testnet_readiness_passed=", report.get("signed_testnet_readiness_passed"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
