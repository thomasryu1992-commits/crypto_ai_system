from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_3_disabled_signed_testnet_executor_review import (
    persist_phase7_3_disabled_signed_testnet_executor_review_report,
)


def main() -> None:
    report = persist_phase7_3_disabled_signed_testnet_executor_review_report()
    print(report.get("status"))
    print("phase7_3_disabled_executor_review_ready=", report.get("phase7_3_disabled_executor_review_ready"))
    print("submit_order_blocked_review_only=", report.get("submit_order_blocked_review_only"))
    print("cancel_order_blocked_review_only=", report.get("cancel_order_blocked_review_only"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("exchange_endpoint_called=", report.get("exchange_endpoint_called"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
