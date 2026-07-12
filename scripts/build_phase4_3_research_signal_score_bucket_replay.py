from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report


def main() -> None:
    report = persist_phase4_3_research_signal_score_bucket_replay_report()
    print(report.get("status"))
    print("source_outcome_count=", report.get("source_outcome_count"))
    print("score_bucket_metadata_attached=", report.get("score_bucket_metadata_attached"))
    print("drift_reduced_subset_count=", report.get("drift_reduced_subset_count"))
    print("candidate_readiness_status=", report.get("candidate_readiness_status"))


if __name__ == "__main__":
    main()
