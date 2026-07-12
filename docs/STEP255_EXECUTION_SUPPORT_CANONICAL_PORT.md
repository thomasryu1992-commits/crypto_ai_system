# Step255 v5 Execution Support Canonical Port Batch

## Purpose

Step255 ports the first missing-canonical execution support batch.

## Ported Modules

- `execution.order_models` → `crypto_ai_system.execution.order_models`
- `execution.order_state` → `crypto_ai_system.execution.order_state`
- `execution.mock_exchange` → `crypto_ai_system.execution.mock_exchange`
- `execution.exchange_router` → `crypto_ai_system.execution.exchange_router`

## Root Compatibility

The four root modules are converted into thin re-export wrappers.

## Safety Rule

`exchange_router` remains disabled/review-only.

It must not enable live trading, adapter routing, network calls, or external order submission.

## Expected Result

- `direct_root_import_finding_count` remains `0`.
- `missing_canonical_module_count` decreases from `10` to `6`.
- Root package deletion remains deferred.
