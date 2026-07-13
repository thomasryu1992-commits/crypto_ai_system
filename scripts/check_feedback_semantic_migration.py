from __future__ import annotations

import sys
from pathlib import Path


MAPPINGS = {
    "phase4_outcome_candidate_feedback.py": "outcome_candidate_feedback.py",
    "phase4_1_paper_outcome_sample_accumulation.py": "paper_sample_accumulation.py",
    "phase4_2_signal_drift_candidate_readiness.py": "signal_drift_readiness.py",
    "phase4_3_research_signal_score_bucket_replay.py": "signal_score_replay.py",
    "phase4_4_candidate_profile_review_packet.py": "candidate_review.py",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    legacy_dir = root / "src" / "crypto_ai_system" / "validation"
    canonical_dir = root / "src" / "crypto_ai_system" / "feedback"
    blockers: list[str] = []

    for legacy_name, canonical_name in MAPPINGS.items():
        legacy = legacy_dir / legacy_name
        canonical = canonical_dir / canonical_name

        if not canonical.exists():
            blockers.append(f"CANONICAL_FEEDBACK_MODULE_MISSING:{canonical_name}")
        if not legacy.exists():
            blockers.append(f"LEGACY_WRAPPER_MISSING:{legacy_name}")
            continue

        text = legacy.read_text(encoding="utf-8")
        if "thin compatibility wrapper" not in text.lower():
            blockers.append(f"LEGACY_MODULE_NOT_THIN_WRAPPER:{legacy_name}")
        if len(text.splitlines()) > 12:
            blockers.append(f"LEGACY_WRAPPER_TOO_LARGE:{legacy_name}")

    run_full_cycle = (root / "run_full_cycle.py").read_text(encoding="utf-8")
    if "from crypto_ai_system.feedback.review import run_feedback_review_chain" not in run_full_cycle:
        blockers.append("RUN_FULL_CYCLE_UNIFIED_FEEDBACK_IMPORT_MISSING")
    if "from crypto_ai_system.validation.phase4_" in run_full_cycle:
        blockers.append("RUN_FULL_CYCLE_STILL_IMPORTS_PHASE4_VALIDATION_MODULES")

    for canonical_name in MAPPINGS.values():
        path = canonical_dir / canonical_name
        if path.exists() and "crypto_ai_system.validation.phase4_" in path.read_text(encoding="utf-8"):
            blockers.append(f"CANONICAL_MODULE_IMPORTS_LEGACY_PHASE_PATH:{canonical_name}")

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("FEEDBACK_SEMANTIC_MIGRATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
