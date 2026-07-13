from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.governance.operator_unlock_template import persist_phase6_1_signed_testnet_operator_unlock_request_template_report


def main() -> None:
    report = persist_phase6_1_signed_testnet_operator_unlock_request_template_report()
    print(report.get("status"))
    print("operator_unlock_request_template_created=", report.get("operator_unlock_request_template_created"))
    print("operator_unlock_request_created=", report.get("operator_unlock_request_created"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
