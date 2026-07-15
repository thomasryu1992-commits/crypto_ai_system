# P6 Single Signed Testnet Submit Runtime Action Report

Status: `P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_READY_DISABLED_NO_SUBMIT`

This package adds a separate signed-testnet runtime action boundary for exactly one BTCUSDT testnet order. The default path remains disabled and performs no HTTP request, no signature creation, and no exchange endpoint call.

## Implemented

- Added `src/crypto_ai_system/execution/single_signed_testnet_submit_runtime_action.py`.
- Added `scripts/build_p6_single_signed_testnet_submit_runtime_action.py`.
- Added `tests/agents/test_p6_single_signed_testnet_submit_runtime_action.py`.
- Added P6 latest evidence, summary, registry record, and negative fixture results.

## Runtime guard requirements

A real signed testnet submit is blocked unless all of the following are true in a separate local runtime process:

- P5 action-time boundary is valid.
- The operator provides the exact runtime arming phrase.
- The action is testnet-only and BTCUSDT-only.
- Max order count is exactly one.
- Metadata-only testnet secret binding is valid.
- Hot-path PreOrderRiskGate is fresh and signed-testnet passing.
- Endpoint time sync is fresh.
- Duplicate submit lock is acquired.
- Idempotency key is not already seen.
- Manual/config kill switch is safe.
- Hard notional and daily loss caps are respected.
- A real signed-testnet endpoint adapter is explicitly attached.
- The operator explicitly allows the runtime network call.

## Current evidence

- `actual_order_submission_performed=false`
- `actual_testnet_order_submitted=false`
- `order_endpoint_called=false`
- `http_request_sent=false`
- `signature_created=false`
- `signed_request_created=false`
- `real_exchange_order_id_present=false`
- `secret_value_accessed=false`
- `secret_value_logged=false`
- `testnet_order_submission_allowed=false`
- `live_canary_execution_enabled=false`
- `live_scaled_execution_enabled=false`

## Evidence files

- `storage/latest/p6_single_signed_testnet_submit_runtime_action_report.json`
- `storage/latest/p6_single_signed_testnet_submit_runtime_action_summary.json`
- `storage/latest/p6_single_signed_testnet_submit_runtime_action_negative_fixture_results.json`
- `storage/latest/p6_single_signed_testnet_submit_runtime_action_registry_record.json`

## Negative fixtures

The P6 negative fixture suite blocks:

- missing runtime arming phrase
- submit requested without operator network allowance
- submit requested without real signed-testnet adapter
- stale runtime risk gate
- duplicate idempotency
- kill switch enabled
- hard cap exceeded
- invalid secret scope

## Next step

P7 should implement the post-submit evidence intake path for the future case where an externally armed local runtime performs the single signed testnet order. That includes order-id intake, status polling evidence, cancel boundary evidence, signed-testnet reconciliation, and signed-testnet session close validation.
