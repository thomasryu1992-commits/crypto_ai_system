from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report


def main() -> None:
    report = persist_phase4_1_paper_outcome_sample_accumulation_report()
    print(report["status"])
    print("outcome_count=", report.get("outcome_count"))
    print("closed_count=", report.get("closed_count"))
    print("performance_status=", report.get("performance_report_status"))
    print("candidate_profile_status=", report.get("candidate_profile_status"))


if __name__ == "__main__":
    main()
