from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_2_executor_enablement_review_packet import persist_phase7_2_executor_enablement_review_packet_report


def main() -> None:
    report = persist_phase7_2_executor_enablement_review_packet_report()
    print(report.get("status"))
    print("phase7_2_executor_enablement_review_ready=", report.get("phase7_2_executor_enablement_review_ready"))
    print("actual_executor_enablement_performed=", report.get("actual_executor_enablement_performed"))
    print("phase7_execution_authority=", report.get("phase7_execution_authority"))
    print("phase7_order_submission_authority=", report.get("phase7_order_submission_authority"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
