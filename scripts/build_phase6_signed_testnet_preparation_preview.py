from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import persist_phase6_signed_testnet_preparation_preview_report


def main() -> None:
    report = persist_phase6_signed_testnet_preparation_preview_report()
    print(report.get("status"))
    print("read_only_venue_probe_recorded=", report.get("read_only_venue_probe_recorded"))
    print("metadata_only_key_reference_recorded=", report.get("metadata_only_key_reference_recorded"))
    print("pre_submit_validation_recorded=", report.get("pre_submit_validation_recorded"))
    print("disabled_executor_evidence_recorded=", report.get("disabled_executor_evidence_recorded"))
    print("signed_testnet_preparation_ready=", report.get("signed_testnet_preparation_ready"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))


if __name__ == "__main__":
    main()
