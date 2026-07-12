from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.review_chain_state_doctor import persist_phase7_1_review_chain_state_doctor_report


def main() -> None:
    report = persist_phase7_1_review_chain_state_doctor_report()
    root = report.get("root_cause_diagnosis") or {}
    print(report.get("status"))
    print("phase7_1_chain_ready_review_only=", report.get("phase7_1_chain_ready_review_only"))
    print("first_blocked_step=", root.get("first_blocked_step"))
    print("first_blocked_reasons=", root.get("first_blocked_reasons"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
