from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

# Historical command compatibility. Active implementation is semantic, not phase-bound.
from crypto_ai_system.feedback.outcome_candidate_feedback import (
    persist_phase4_outcome_candidate_feedback_report,
)


def main() -> None:
    report = persist_phase4_outcome_candidate_feedback_report()
    print(report.get("status"))


if __name__ == "__main__":
    main()
