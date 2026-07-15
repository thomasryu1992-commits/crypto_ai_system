# Phase 4.3 ResearchSignal Score Bucket & Drift Reduction Replay Report

## Goal
Attach pre-trade ResearchSignal score bucket metadata to Phase 4.1 paper outcomes and replay drift/candidate readiness analysis without using post-outcome leakage.

## Added
- `src/crypto_ai_system/validation/phase4_3_research_signal_score_bucket_replay.py`
- `scripts/build_phase4_3_research_signal_score_bucket_replay.py`
- `tests/agents/test_phase4_3_research_signal_score_bucket_replay.py`

## Expected artifacts
- `storage/latest/phase4_3_research_signal_score_bucket_replay_report.json`
- `storage/latest/phase4_3_research_signal_score_bucket_replay_registry_record.json`
- `storage/latest/paper_outcome_score_bucket_enriched_outcomes.json`
- `storage/latest/drift_reduced_candidate_profile_draft.json`
- `storage/registries/phase4_3_research_signal_score_bucket_replay_registry.jsonl`

## Safety
This phase is review-only and paper-only. It may create a drift-reduced candidate profile draft, but it must not apply the candidate profile, mutate `settings.yaml`, mutate runtime `score_weights`, create an approval packet, enable signed testnet execution, or submit any order.
