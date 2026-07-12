# Source Health Agent Contract

## Contract

`source-health` creates a review-only JSON artifact using the `source_health_review_v1` contract.

The artifact records whether required price data and optional sources are connected, fresh, stale, or missing. Price data is the only hard-required source. Optional sources are marked `neutral_due_to_missing` when unavailable.

## Safety invariants

The source-health artifact must never grant execution permission. These fields must remain false:

- `trading_candidate_allowed`
- `paper_candidate_eligible`
- `signed_testnet_candidate_eligible`
- `live_candidate_eligible`
- `execution_permission_granted`
- `stage_transition_allowed`
- `order_endpoint_called`
- `secret_value_accessed`

Fallback, sample, synthetic, mock, stale, or hidden-missing source evidence must block signed testnet/live candidacy.

## Local Launcher behavior

In Local Launcher dry-run mode, price data is not assumed to be connected. The generated artifact records:

- `price_data_hard_required: true`
- `price_data_connected: false`
- `fresh_price_data_available: false`
- optional sources as `neutral_due_to_missing`

The artifact is transparency evidence only, not trading authorization.
