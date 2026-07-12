from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report


def main() -> None:
    report = persist_phase4_4_candidate_profile_review_packet_report()
    print(report.get("status"))
    print("candidate_review_packet_created=", report.get("candidate_review_packet_created"))
    print("approval_packet_draft_created=", report.get("approval_packet_draft_created"))
    print("approval_intake_status=", report.get("approval_intake_status"))
    print("signed_testnet_unlock_allowed=", report.get("signed_testnet_unlock_allowed"))


if __name__ == "__main__":
    main()
