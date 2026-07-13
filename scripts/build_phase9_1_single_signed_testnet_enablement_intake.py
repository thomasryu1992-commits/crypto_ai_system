from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
    persist_phase9_1_actual_operator_approval_intake_hardening_report,
    persist_phase9_1_single_signed_testnet_enablement_intake_report,
)


def main() -> None:
    report = persist_phase9_1_single_signed_testnet_enablement_intake_report(run_phase8_4_first=False)
    hardening_report = persist_phase9_1_actual_operator_approval_intake_hardening_report(run_phase9_1_first=False)
    print(report.get("status"))
    print("phase9_1_single_signed_testnet_enablement_intake_ready=", report.get("phase9_1_single_signed_testnet_enablement_intake_ready"))
    print("phase9_1_actual_enablement_approval_complete=", report.get("phase9_1_actual_enablement_approval_complete"))
    print("phase9_2_single_testnet_order_submit_may_begin=", report.get("phase9_2_single_testnet_order_submit_may_begin"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("order_endpoint_called=", report.get("order_endpoint_called"))
    print("http_request_sent=", report.get("http_request_sent"))
    print("signature_created=", report.get("signature_created"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("block_reasons=", report.get("block_reasons"))
    print("actual_operator_approval_hardening_status=", hardening_report.get("status"))
    print("actual_operator_approval_template_ready=", hardening_report.get("phase9_1_actual_operator_approval_template_ready"))
    print("actual_operator_approval_values_complete=", hardening_report.get("phase9_1_actual_operator_approval_values_complete"))


if __name__ == "__main__":
    main()
