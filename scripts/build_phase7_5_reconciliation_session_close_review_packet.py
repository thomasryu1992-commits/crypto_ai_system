from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_5_reconciliation_session_close_review_packet import (
    persist_phase7_5_reconciliation_session_close_review_packet_report,
)


def main() -> None:
    report = persist_phase7_5_reconciliation_session_close_review_packet_report()
    print(report.get("status"))
    print("phase7_5_review_packet_ready=", report.get("phase7_5_review_packet_ready"))
    print("promotion_guard_passed=", report.get("promotion_guard_passed"))
    print("disabled_execution_reconciled_review_only=", report.get("disabled_execution_reconciled_review_only"))
    print("session_closed_review_only=", report.get("session_closed_review_only"))
    print("reconciliation_mismatch=", report.get("reconciliation_mismatch"))
    print("observed_fill_count=", report.get("observed_fill_count"))
    print("observed_position_delta=", report.get("observed_position_delta"))
    print("observed_balance_delta=", report.get("observed_balance_delta"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("external_order_submission_performed=", report.get("external_order_submission_performed"))
    print("exchange_endpoint_called=", report.get("exchange_endpoint_called"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
