from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_14_future_executor_operator_decision_packet import (
    persist_phase7_14_future_executor_operator_decision_packet_report,
)


def main() -> None:
    report = persist_phase7_14_future_executor_operator_decision_packet_report()
    print(report.get("status"))
    print("phase7_14_operator_decision_packet_ready=", report.get("phase7_14_operator_decision_packet_ready"))
    print("future_executor_operator_decision_packet_created=", report.get("future_executor_operator_decision_packet_created"))
    print("operator_decision_guard_passed=", report.get("operator_decision_guard_passed"))
    print("future_operator_decision_required_before_any_order=", report.get("future_operator_decision_required_before_any_order"))
    print("actual_operator_decision_recorded=", report.get("actual_operator_decision_recorded"))
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
