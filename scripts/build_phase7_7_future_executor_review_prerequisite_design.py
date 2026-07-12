from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase7_7_future_executor_review_prerequisite_design import (
    persist_phase7_7_future_executor_review_prerequisite_design_report,
)


def main() -> None:
    report = persist_phase7_7_future_executor_review_prerequisite_design_report()
    print(report.get("status"))
    print("phase7_7_prerequisite_design_ready=", report.get("phase7_7_prerequisite_design_ready"))
    print("future_executor_prerequisite_packet_created=", report.get("future_executor_prerequisite_packet_created"))
    print("future_executor_prerequisite_guard_passed=", report.get("future_executor_prerequisite_guard_passed"))
    print("future_executor_review_prerequisites_ready_review_only=", report.get("future_executor_review_prerequisites_ready_review_only"))
    print("metadata_only_key_reference_required=", report.get("metadata_only_key_reference_required"))
    print("fresh_pre_submit_payload_validation_required=", report.get("fresh_pre_submit_payload_validation_required"))
    print("fresh_pre_order_risk_gate_recheck_required=", report.get("fresh_pre_order_risk_gate_recheck_required"))
    print("manual_kill_switch_confirmation_required=", report.get("manual_kill_switch_confirmation_required"))
    print("future_executor_review_required_before_any_order=", report.get("future_executor_review_required_before_any_order"))
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
