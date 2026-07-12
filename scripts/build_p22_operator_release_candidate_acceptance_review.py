from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_release_candidate_acceptance_review import persist_operator_release_candidate_acceptance_review


def main() -> None:
    cfg = load_config(Path.cwd())
    report = persist_operator_release_candidate_acceptance_review(cfg)
    print(report["status"])
    print(report["p22_operator_release_candidate_acceptance_review_sha256"])


if __name__ == "__main__":
    main()
