# Price Feature Snapshot Agent Contract

Version: 0.286.0-agent.14

## Purpose

`price_feature_snapshot_v1` links a validated local OHLCV CSV data snapshot to a minimal review-only feature matrix that can be referenced by `source-health`, `daily`, `scan`, and `signal` command artifacts.

This contract does not grant trading permission. It only records lineage:

```text
data_snapshot_id -> feature_snapshot_id -> feature_matrix_sha256 -> research_signal_id
```

## Creation requirements

A feature snapshot may be created only when all of the following are true:

- `price_data_connected=true`
- `fresh_price_data_available=true`
- `price_csv_schema_valid=true`
- `sample_flag=false`
- `fallback_flag=false`
- `synthetic_flag=false`
- `mock_flag=false`
- required price data is not stale

Sample, fixture, mock, synthetic, fallback, invalid, stale, or missing CSV inputs must set:

```text
feature_snapshot_created=false
feature_snapshot_status=blocked_review_only
feature_snapshot_blocked_by_sample_stale_invalid=true
```

A blocked placeholder `feature_snapshot_id` may be emitted for audit lineage continuity, but it is not a usable feature snapshot for signed testnet or live candidacy.

## Minimal feature fields

The local CSV dry-run feature matrix includes:

```text
latest_close
previous_close
close_return_1
high_low_range_pct
latest_volume
row_count
```

The matrix is hashed as `feature_matrix_sha256`; the snapshot manifest is hashed as `feature_snapshot_manifest_sha256`.

## Safety invariants

All feature snapshot artifacts and stdout fields must keep:

```text
review_only=true
trading_candidate_allowed=false
paper_candidate_eligible=false
signed_testnet_candidate_eligible=false
live_candidate_eligible=false
execution_permission_granted=false
stage_transition_allowed=false
```

The feature snapshot is evidence for review and debugging only. It must not submit orders, create order intents, read secrets, mutate runtime settings, or unlock stage transitions.
