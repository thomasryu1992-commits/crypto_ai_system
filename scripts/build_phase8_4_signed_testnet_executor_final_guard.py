from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase8_4_signed_testnet_executor_final_guard import (
    persist_phase8_4_signed_testnet_executor_final_guard_report,
)


def main() -> None:
    report = persist_phase8_4_signed_testnet_executor_final_guard_report()
    print(report.get("status"))
    print("phase8_4_signed_testnet_executor_final_guard_ready=", report.get("phase8_4_signed_testnet_executor_final_guard_ready"))
    print("signed_testnet_executor_final_guard_guard_passed=", report.get("signed_testnet_executor_final_guard_guard_passed"))
    print("phase9_1_single_signed_testnet_enablement_intake_may_begin=", report.get("phase9_1_single_signed_testnet_enablement_intake_may_begin"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("order_endpoint_called=", report.get("order_endpoint_called"))
    print("http_request_sent=", report.get("http_request_sent"))
    print("signature_created=", report.get("signature_created"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
