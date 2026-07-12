from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_17_final_pre_executor_review_packet import (
    persist_phase7_17_final_pre_executor_review_packet_report,
)


def main() -> None:
    report = persist_phase7_17_final_pre_executor_review_packet_report()
    print(report.get("status"))
    print("phase7_final_pre_executor_review_ready=", report.get("phase7_final_pre_executor_review_ready"))
    print("phase7_review_chain_complete=", report.get("phase7_review_chain_complete"))
    print("final_pre_executor_review_guard_passed=", report.get("final_pre_executor_review_guard_passed"))
    print("phase8_preparation_review_may_begin=", report.get("phase8_preparation_review_may_begin"))
    print("actual_phase8_approval_granted=", report.get("actual_phase8_approval_granted"))
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
