from __future__ import annotations

from pathlib import Path


MAPPINGS = {
    "phase4_outcome_candidate_feedback.py": "outcome_candidate_feedback.py",
    "phase4_1_paper_outcome_sample_accumulation.py": "paper_sample_accumulation.py",
    "phase4_2_signal_drift_candidate_readiness.py": "signal_drift_readiness.py",
    "phase4_3_research_signal_score_bucket_replay.py": "signal_score_replay.py",
    "phase4_4_candidate_profile_review_packet.py": "candidate_review.py",
}


def test_phase4_legacy_modules_are_thin_compatibility_wrappers() -> None:
    root = Path(__file__).resolve().parents[1]
    legacy_dir = root / "src" / "crypto_ai_system" / "validation"
    canonical_dir = root / "src" / "crypto_ai_system" / "feedback"

    for legacy_name, canonical_name in MAPPINGS.items():
        legacy = legacy_dir / legacy_name
        canonical = canonical_dir / canonical_name

        assert canonical.exists(), canonical
        assert legacy.exists(), legacy

        text = legacy.read_text(encoding="utf-8")
        assert "thin compatibility wrapper" in text.lower()
        assert "from crypto_ai_system.feedback." in text
        assert len(text.splitlines()) <= 12


def test_run_full_cycle_uses_only_unified_feedback_entry_point() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "run_full_cycle.py").read_text(encoding="utf-8")

    assert "from crypto_ai_system.feedback.review import run_feedback_review_chain" in text
    assert "persist_phase4_1_paper_outcome_sample_accumulation_report" not in text
    assert "persist_phase4_2_signal_drift_candidate_readiness_report" not in text
    assert "persist_phase4_3_research_signal_score_bucket_replay_report" not in text
    assert "persist_phase4_4_candidate_profile_review_packet_report" not in text


def test_canonical_phase4_modules_do_not_import_old_phase4_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    canonical_dir = root / "src" / "crypto_ai_system" / "feedback"

    for canonical_name in MAPPINGS.values():
        text = (canonical_dir / canonical_name).read_text(encoding="utf-8")
        assert "crypto_ai_system.validation.phase4_" not in text
