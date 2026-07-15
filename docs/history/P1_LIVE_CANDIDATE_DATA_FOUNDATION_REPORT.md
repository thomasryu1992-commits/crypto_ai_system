# P1 Live Candidate Data Foundation - Review Only

## Status

Completed as a review-only data-foundation hardening step. This update does not enable signed testnet execution, live canary execution, live scaled execution, order submission, cancel submission, runtime settings mutation, score-weight mutation, or automatic promotion.

## Implemented

- Added explicit live-candidate data foundation checks to `src/crypto_ai_system/data/data_snapshot_manifest.py`.
- Price data remains hard-required.
- Price freshness can be enforced with `data.live_candidate.max_price_age_sec`, `data.live_candidate_price_max_age_sec`, or `data.price_source_max_age_sec`.
- Data Snapshot Manifest now records:
  - `timestamp_start_utc`
  - `timestamp_end_utc`
  - `price_timestamp_start_utc`
  - `price_timestamp_end_utc`
  - `price_source_age_sec`
  - `price_source_max_age_sec`
  - `price_source_stale`
  - `optional_data_health_summary`
  - `live_candidate_eligibility_checks`
  - `live_candidate_block_reasons`
  - `live_candidate_data_foundation_version`
- Fallback, synthetic, sample, mock, and stale price data fail closed for live-candidate eligibility.
- Optional source missing remains explicit `neutral_due_to_missing` and blocks live-candidate eligibility.
- Optional stale source health blocks live-candidate eligibility.
- Data Snapshot Registry now carries price freshness fields, `mock_flag`, and live-candidate block reasons.
- Source QA now blocks `blocked_mock` as `BLOCK_MOCK_DATA`.
- Paper Data Quality Gate now exposes `live_candidate_data_foundation_eligible` separately from runtime `live_candidate_eligible`.
- Backtest feature-matrix behavior is covered by a future-data leakage negative test.

## Current Package Evidence

The current packaged latest evidence remains review-only. `paper_candidate_allowed=true` is possible for existing latest evidence, but `live_candidate_data_foundation_eligible=false` because current latest evidence still has optional source missing and lacks the full Data Snapshot Manifest price timestamp range expected for live-candidate promotion.

This is intentional. P1 defines and tests the eligibility boundary; it does not manufacture live evidence or promote the package.

## Validation

Focused P1/P0 regression passed:

```text
29 passed
```

Additional validation passed:

```text
python -m compileall -q src config tests scripts
python scripts/status_consistency_checker.py .
python scripts/lint_agents.py
python scripts/validate_agent_contracts.py
python scripts/validate_agent_outputs.py
python scripts/run_agent_evals.py
```

## Safety State

```text
signed_testnet_unlock_authority=false
live_execution_unlock_authority=false
runtime_permission_source=false
order_submission_performed=false
live_candidate_eligible=false in runtime/report authority surfaces
```

## Next Step

P2 should move into Paper Operation Validation:

- regenerate fresh local BTC price lineage with the new manifest fields,
- reduce optional source missing where real public/read-only sources are available,
- repeatedly run paper strategy validation,
- accumulate enough closed paper outcomes,
- measure signal-to-outcome drift,
- prepare accepted-for-review candidate profile criteria without applying it to runtime.
