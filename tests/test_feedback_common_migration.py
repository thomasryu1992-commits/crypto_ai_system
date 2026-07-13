from __future__ import annotations

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


def test_phase4_canonical_modules_use_shared_feedback_common_utilities() -> None:
    root = Path(__file__).resolve().parents[1]
    feedback_dir = root / "src" / "crypto_ai_system" / "feedback"

    for name in CANONICAL_MODULES:
        text = (feedback_dir / name).read_text(encoding="utf-8")
        assert "from crypto_ai_system.feedback.common import" in text

        for helper in DUPLICATE_HELPERS:
            assert f"def {helper}(" not in text, f"{name} still defines {helper}"


def test_feedback_common_remains_review_only_utility_without_execution_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "src" / "crypto_ai_system" / "feedback" / "common.py"
    ).read_text(encoding="utf-8")

    assert "place_order" not in text
    assert "cancel_order" not in text
    assert "signed_order_executor" not in text
    assert "external_runtime_packages" not in text
