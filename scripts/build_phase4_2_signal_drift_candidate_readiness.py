from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

# Historical command compatibility. Active implementation is semantic, not phase-bound.
from crypto_ai_system.feedback.signal_drift_readiness import (
    persist_phase4_2_signal_drift_candidate_readiness_report,
)


def main() -> None:
    report = persist_phase4_2_signal_drift_candidate_readiness_report()
    overall = report.get("overall_summary") or {}
    print(report["status"])
    print("source_outcome_count=", report.get("source_outcome_count"))
    print("closed_count=", overall.get("closed_count"))
    print("overall_drift_rate=", overall.get("drift_rate"))
    print("readiness_subset_count=", report.get("readiness_subset_count"))
    print("candidate_readiness_status=", report.get("candidate_readiness_status"))


if __name__ == "__main__":
    main()
