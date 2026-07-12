from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase8_3_hot_path_preorder_risk_gate import (
    persist_phase8_3_hot_path_preorder_risk_gate_report,
)


def main() -> None:
    report = persist_phase8_3_hot_path_preorder_risk_gate_report()
    print(report.get("status"))
    print("phase8_3_hot_path_risk_gate_ready=", report.get("phase8_3_hot_path_risk_gate_ready"))
    print("hot_path_preorder_risk_gate_guard_passed=", report.get("hot_path_preorder_risk_gate_guard_passed"))
    print("phase8_4_final_guard_may_begin=", report.get("phase8_4_final_guard_may_begin"))
    print("exchange_endpoint_called=", report.get("exchange_endpoint_called"))
    print("order_endpoint_called=", report.get("order_endpoint_called"))
    print("http_request_sent=", report.get("http_request_sent"))
    print("signature_created=", report.get("signature_created"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
