from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_2_single_testnet_order_submit import (
    persist_phase9_2_single_testnet_order_submit_report,
)


def main() -> None:
    report = persist_phase9_2_single_testnet_order_submit_report(run_phase9_1_first=False)
    print(report.get("status"))
    print("phase9_2_single_testnet_order_submit_attempt_recorded=", report.get("phase9_2_single_testnet_order_submit_attempt_recorded"))
    print("phase9_2_single_testnet_order_submit_blocked_fail_closed=", report.get("phase9_2_single_testnet_order_submit_blocked_fail_closed"))
    print("phase9_2_order_submission_authorized=", report.get("phase9_2_order_submission_authorized"))
    print("phase9_3_status_polling_may_begin=", report.get("phase9_3_status_polling_may_begin"))
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
