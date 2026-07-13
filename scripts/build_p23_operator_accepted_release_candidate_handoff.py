from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_accepted_release_candidate_handoff import persist_operator_accepted_release_candidate_handoff


def main() -> None:
    cfg = load_config(Path.cwd())
    report = persist_operator_accepted_release_candidate_handoff(cfg)
    print(report["status"])
    print(report["p23_operator_accepted_release_candidate_handoff_sha256"])


if __name__ == "__main__":
    main()
