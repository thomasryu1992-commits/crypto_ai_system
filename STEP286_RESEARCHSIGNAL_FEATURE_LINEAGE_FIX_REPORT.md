# Step286 ResearchSignal Feature Lineage Fix Report

## Goal
Fix the ResearchSignal creation order so each ResearchSignal carries complete feature lineage.

## Problem Fixed
Before Step286, `storage/latest/research_signal.json` could contain:

```text
feature_snapshot_id=None
feature_matrix_sha256=None
```

This violated the canonical ResearchSignal v2 lineage requirement that a signal preserve its data snapshot, feature snapshot, feature matrix hash, and source bundle hash.

## Changes Applied
- Updated `src/crypto_ai_system/research/research_bot.py` so the live feature matrix manifest is built before `build_research_signal()`.
- Injected the feature manifest into the latest feature snapshot before signal creation.
- Updated `src/crypto_ai_system/features/research_feature_matrix.py` so `feature_snapshot_id` is stable before and after persistence by excluding storage path metadata from the stable ID payload.
- Updated `src/crypto_ai_system/research/raw_score_pipeline.py` so the persisted live feature manifest is materialized back into the payload/signal before writing `storage/latest/research_signal.json`.
- Added regression tests for in-memory lineage, persistence stability, and latest-signal materialization.

## Required Lineage After Fix
```text
data_snapshot_id: present
feature_snapshot_id: present
feature_matrix_sha256: present
source_bundle_sha256: present
research_signal_id: present
```

## Tests Added
- `tests/test_step286_researchsignal_lineage_fix.py`

## Validation Result
- `PYTHONPATH=src:. pytest -q tests/test_step286_*.py` — PASS
- Focused Step258~282 + Step286 regression — 154 passed
- `PYTHONPATH=src:. python run_operational_dry_run.py` — PASSED
- `PYTHONPATH=src:. python run_full_cycle.py` — completed with `BLOCK_DATA_HEALTH`, `NO_ORDER`

## Runtime Evidence From Local Verification
After running the raw-to-score pipeline and full-cycle check, latest ResearchSignal carried:

```text
data_snapshot_id=data_snapshot_2c4f3e6d0d946e5a93bdedd3
feature_snapshot_id=feature_snapshot_a3d37e86487de1637a29
feature_matrix_sha256=721304635cb46d57ff577e715298616495a2ffb2a5bde6f73d2d850a4af2749f
source_bundle_sha256=d1fae841b53c704872ff5a631ca4707f5e7537b37b35d70bfc85f033947c2a74
live_candidate_eligible=false
```

`live_candidate_eligible=false` is expected because optional data is disabled/missing in the local verification environment. This blocks live/signed-testnet eligibility as intended.

## Result
Step286 ResearchSignal lineage fix is complete. This step strengthens auditability only; it does not unlock signed testnet or live execution.
