from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_signed_testnet_validation_design_guard import persist_phase7_signed_testnet_validation_design_guard_report


def main() -> None:
    report = persist_phase7_signed_testnet_validation_design_guard_report()
    print(report.get("status"))
    print("phase7_design_ready_review_only=", report.get("phase7_design_ready_review_only"))
    print("phase7_execution_authority=", report.get("phase7_execution_authority"))
    print("phase7_order_submission_authority=", report.get("phase7_order_submission_authority"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
