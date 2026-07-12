from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_1_operator_supplied_approval_fixture import (
    persist_phase9_1_operator_supplied_approval_fixture_report,
)
from crypto_ai_system.validation.phase9_2_submit_guard_recheck import (
    persist_phase9_2_submit_guard_recheck_report,
)


def main() -> None:
    fixture_report = persist_phase9_1_operator_supplied_approval_fixture_report(run_phase9_1_hardening_first=True)
    recheck_report = persist_phase9_2_submit_guard_recheck_report(run_operator_fixture_first=False)
    print(fixture_report.get("status"))
    print("phase9_1_operator_supplied_approval_fixture_validated=", fixture_report.get("phase9_1_operator_supplied_approval_fixture_validated"))
    print("phase9_2_submit_guard_recheck_may_begin=", fixture_report.get("phase9_2_submit_guard_recheck_may_begin"))
    print(recheck_report.get("status"))
    print("phase9_2_submit_guard_recheck_ready=", recheck_report.get("phase9_2_submit_guard_recheck_ready"))
    print("phase9_2_pre_submit_conditions_ready_for_review_only=", recheck_report.get("phase9_2_pre_submit_conditions_ready_for_review_only"))
    print("phase9_2_order_submission_authorized=", recheck_report.get("phase9_2_order_submission_authorized"))
    print("phase9_3_status_polling_may_begin=", recheck_report.get("phase9_3_status_polling_may_begin"))
    print("testnet_order_submission_allowed=", recheck_report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", recheck_report.get("place_order_enabled"))
    print("cancel_order_enabled=", recheck_report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", recheck_report.get("signed_order_executor_enabled"))
    print("order_endpoint_called=", recheck_report.get("order_endpoint_called"))
    print("http_request_sent=", recheck_report.get("http_request_sent"))
    print("signature_created=", recheck_report.get("signature_created"))
    print("actual_order_submission_performed=", recheck_report.get("actual_order_submission_performed"))


if __name__ == "__main__":
    main()
