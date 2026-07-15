# Step298 Candidate Profile Registry Report

## Goal

Add a review-only Candidate Profile Registry after Step297 Performance Report Generator.

Step298 converts a validated performance report into a candidate profile draft only when the performance report is recorded, recommends `create_candidate_profile_draft`, has positive expectancy, and has no blockers or unsafe side-effect flags.

## Implemented

- Added `src/crypto_ai_system/feedback/candidate_profile_registry.py`.
- Added `storage/latest/candidate_profile.json` runtime evidence generation.
- Added `storage/latest/candidate_profile_registry_record.json` runtime evidence generation.
- Added append-only `storage/registries/candidate_profile_registry.jsonl` evidence generation.
- Connected `run_full_cycle.py` and `run_operational_dry_run.py` to run candidate profile generation after performance report generation.
- Updated README, master context, status checker, CI workflow, and chunked full-regression suite references to Step298.

## Candidate Profile Fields

The candidate profile draft preserves:

- `candidate_profile_id`
- `source_report_id`
- `source_report_hash`
- `profile_version`
- `strategy_family`
- `target_timeframe`
- `allowed_direction`
- `expected_edge_reason`
- `data_quality_score`
- `paper_priority_score`
- `risk_complexity_score`
- `feature_matrix_sha256`
- `profile_candidate_hash`
- `live_ineligible_reason`
- `status`
- source outcome IDs and hashes through `performance_snapshot`

## Safety Constraints Preserved

Step298 does not:

- apply candidate profiles
- create approval packets
- create settings-write previews
- mutate `settings.yaml`
- mutate runtime score weights
- enable signed testnet execution
- submit external orders
- enable live trading
- allow automatic promotion

## Runtime Evidence

Current full cycle remains fail-closed because data health blocks order creation.

- `run_full_cycle.py`: `BLOCK_DATA_HEALTH / NO_ORDER`
- `performance_report.status`: `PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE`
- `candidate_profile.creation_status`: `CANDIDATE_PROFILE_BLOCKED_PERFORMANCE_REPORT_NOT_READY`
- `candidate_profile.status`: `rejected`
- `candidate_profile.candidate_profile_created`: `false`

This is expected because the current runtime has insufficient closed paper outcome samples.

## Validation

- `compileall`: PASSED
- `status_consistency_checker`: PASSED
- `tests/test_step298_candidate_profile_registry.py`: 6 passed
- `tests/test_step282_*.py tests/test_step298_*.py`: 11 passed
- `tests/test_step294_*.py ... tests/test_step298_*.py`: 36 passed
- `tests/test_step258_*.py ... tests/test_step280_*.py`: 138 passed
- `tests/test_step281_*.py ... tests/test_step298_*.py`: 103 passed
- `run_operational_dry_run.py`: PASSED
- `run_full_cycle.py`: BLOCK_DATA_HEALTH / NO_ORDER

## Next Step

Step299 — Prompt / Profile Library.
