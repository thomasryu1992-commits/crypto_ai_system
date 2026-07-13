# ResearchSignal v2 Agent Package Contract

This package emits `signal` command output as a review-only ResearchSignal v2 JSON artifact.

## Scope

- Command: `signal`
- Artifact format: JSON
- Default storage: `data/reports/research_signal_{symbol}_{datetime}.json`
- Launcher stdout contract: final stdout line is JSON

## Required lineage fields

The artifact must include:

- `research_signal_id`
- `signal_version`
- `profile_id`
- `profile_version`
- `config_version`
- `data_snapshot_id`
- `feature_snapshot_id`
- `feature_matrix_sha256`
- `source_bundle_sha256`
- `data_snapshot_manifest_sha256`
- `optional_data_health`
- `missing_optional_source_count`
- `stale_optional_source_count`
- `created_at_utc`

## Review-only safety fields

The package wrapper must keep these values false:

- `live_eligibility`
- `live_candidate_eligible`
- `signed_testnet_candidate_eligible`
- `paper_candidate_eligible`
- `live_trading_enabled`
- `order_execution_enabled`
- `auto_position_open_enabled`
- `withdrawal_enabled`
- `fund_transfer_enabled`
- `execution_permission_granted`
- `stage_transition_allowed`
- `order_endpoint_called`
- `secret_value_accessed`

## Optional data policy

Missing optional data is explicit and neutral for reporting only:

- `neutral_due_to_missing: true`
- `missing_optional_data_neutral: true`
- optional sources set to `neutral_due_to_missing`

This must never be interpreted as signed testnet or live candidate eligibility.

## Launcher boundary

The Crypto_AI_System ZIP only emits package-owned artifacts. Agent OS import, registry mutation, Telegram routing, duplicate import policy, and rollback remain Launcher-owned responsibilities.
