# P4 Signed Testnet One-Order Runtime Package — Review Only / Disabled

## Status

P4 adds a separate signed-testnet one-order runtime package boundary. It prepares the runtime controls needed before a future explicit single signed-testnet submit action, but it does not submit an order and does not enable any execution flag.

Latest status:

```text
P4_SIGNED_TESTNET_ONE_ORDER_RUNTIME_PACKAGE_READY_REVIEW_ONLY_DISABLED
```

## Added implementation

- `src/crypto_ai_system/execution/signed_testnet_one_order_runtime_package.py`
- `scripts/build_p4_signed_testnet_one_order_runtime_package.py`
- `tests/agents/test_p4_signed_testnet_one_order_runtime_package.py`

## Runtime controls covered

- Metadata-only testnet secret binding evidence.
- No API key, API secret, private key, passphrase, or secret file value in payloads.
- Testnet-only key scope validation.
- One-order guard with `max_order_count=1`.
- BTCUSDT symbol scope.
- Side/order type scope.
- Low-notional cap and daily loss cap validation.
- Fresh hot-path PreOrderRiskGate requirement.
- Manual kill switch safe-state requirement.
- Idempotency key enforcement.
- Duplicate submit lock validation.
- Disabled place-order / status / cancel endpoint boundaries.
- Post-submit relock policy evidence.
- Negative fixtures for invalid secret fingerprint, duplicate idempotency, hard-cap breach, kill switch engaged, stale risk gate, and already-submitted order count.

## Generated evidence

- `storage/latest/p4_signed_testnet_one_order_runtime_package_report.json`
- `storage/latest/p4_signed_testnet_one_order_runtime_package_summary.json`
- `storage/latest/p4_signed_testnet_runtime_package_negative_fixture_results.json`
- `storage/latest/p4_signed_testnet_one_order_runtime_package_registry_record.json`
- `storage/p4_signed_testnet_runtime_package/p4_signed_testnet_one_order_runtime_package_report.json`

## Safety state

The P4 package is ready only as a review-only runtime boundary. These remain false:

```text
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
external_order_submission_performed=false
place_order_enabled=false
cancel_order_enabled=false
signed_order_executor_enabled=false
order_endpoint_called=false
order_status_endpoint_called=false
cancel_endpoint_called=false
http_request_sent=false
signature_created=false
signed_request_created=false
secret_value_accessed=false
secret_value_logged=false
runtime_settings_mutated=false
score_weights_mutated=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
```

## Verification

Focused regression:

```text
49 passed
```

Covered tests:

- `tests/agents/test_p4_signed_testnet_one_order_runtime_package.py`
- `tests/agents/test_phase_d_candidate_manual_approval_chain.py`
- `tests/agents/test_phase9_2_single_testnet_runtime_submit_wrapper.py`
- `tests/agents/test_phase9_2_submit_guard_recheck.py`
- `tests/test_step304_testnet_secret_metadata_intake_v2.py`
- `tests/test_step306_signed_testnet_pre_submit_validator.py`
- `tests/test_step308_signed_testnet_order_executor.py`
- `tests/test_step309_signed_testnet_reconciliation.py`
- `tests/test_step310_signed_testnet_session_close_report.py`

Additional checks:

```text
compileall: passed
status_consistency_checker: passed
Agent lint: passed
Agent contract validation: passed
Agent output validation: passed
Agent evals: passed
```

## Known boundary

This package does not satisfy the future completion criteria of an actual signed-testnet order session. There is still no real testnet order endpoint call, no real exchange order id, no real status polling response, no real cancel endpoint evidence, and no real exchange-response reconciliation. A later phase must add an explicit runtime submit action with fresh action-time validation and operator-controlled permission.
