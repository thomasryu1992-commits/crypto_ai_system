from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.review_chain_state_doctor import persist_phase7_1_review_chain_state_doctor_report


def main() -> int:
    report = persist_phase7_1_review_chain_state_doctor_report()
    root = report.get("root_cause_diagnosis") or {}
    print(report.get("status"))
    print("phase7_1_chain_ready_review_only=", report.get("phase7_1_chain_ready_review_only"))
    print("first_blocked_step=", root.get("first_blocked_step"))
    print("first_blocked_reasons=", root.get("first_blocked_reasons"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
