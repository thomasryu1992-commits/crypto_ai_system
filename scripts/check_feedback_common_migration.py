from __future__ import annotations

import ast
from pathlib import Path


CANONICAL_MODULES = (
    "outcome_candidate_feedback.py",
    "paper_sample_accumulation.py",
    "signal_drift_readiness.py",
    "signal_score_replay.py",
    "candidate_review.py",
)

DUPLICATE_HELPERS = {
    "_latest_dir",
    "_storage_dir",
    "_read_latest_json",
    "_hash_latest",
    "_bool",
    "_float",
    "_text",
    "_safe_text",
    "_json_safe",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    feedback_dir = root / "src" / "crypto_ai_system" / "feedback"
    blockers: list[str] = []

    common = feedback_dir / "common.py"
    if not common.exists():
        blockers.append("FEEDBACK_COMMON_MODULE_MISSING")

    for name in CANONICAL_MODULES:
        path = feedback_dir / name
        if not path.exists():
            blockers.append(f"CANONICAL_FEEDBACK_MODULE_MISSING:{name}")
            continue

        text = path.read_text(encoding="utf-8")
        if "from crypto_ai_system.feedback.common import" not in text:
            blockers.append(f"SHARED_COMMON_IMPORT_MISSING:{name}")

        tree = ast.parse(text, filename=str(path))
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for helper in sorted(DUPLICATE_HELPERS & defined):
            blockers.append(f"DUPLICATE_HELPER_REMAINS:{name}:{helper}")

    if blockers:
        for blocker in sorted(set(blockers)):
            print(blocker)
        return 2

    print("FEEDBACK_COMMON_UTILS_MIGRATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
