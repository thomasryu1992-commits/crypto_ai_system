# Step257 v5 Deferred Execution Stub Policy

## Purpose

Step257 locks the final two remaining `CANONICAL_MODULE_MISSING` root modules as explicit disabled compatibility surfaces:

- `execution.live_executor`
- `execution.testnet_executor`

These modules are intentionally **not** canonical live/testnet execution implementations.

## Locked Decision

1. `execution.live_executor` and `execution.testnet_executor` remain root-level compatibility surfaces.
2. They must not be ported into `src/crypto_ai_system/execution/` as canonical live/testnet executors.
3. Their behavior is fail-closed:
   - `LiveExecutor.place_order()` raises `NotImplementedError`.
   - `TestnetExecutor.place_order()` returns `TESTNET_ORDER_SKIPPED` when `ENABLE_TESTNET_ORDERS` is false.
   - `TestnetExecutor.place_order()` raises `NotImplementedError` when `ENABLE_TESTNET_ORDERS` is true.
   - `TestnetExecutor.recover_unknown_order()` returns `RECOVERY_QUERY_NOT_IMPLEMENTED` only and writes a local audit row.
4. `missing_canonical_module_count` remains exactly `2`.
5. Root package deletion remains postponed.

## Why They Are Not Canonicalized

Live execution and signed testnet execution require a separate architecture for exchange adapters, credentials, order lifecycle reconciliation, rate-limit handling, idempotency, balance/margin checks, fee/slippage/min-size validation, operator approvals, monitoring, and rollback behavior.

The root compatibility modules are legacy stubs, not a safe source of truth for canonical live execution.

## Safety Invariants

The following values must remain false:

- `PORT_TO_CANONICAL_ALLOWED`
- `CANONICAL_LIVE_EXECUTION_PORT_ALLOWED`
- `CANONICAL_TESTNET_EXECUTION_PORT_ALLOWED` for `testnet_executor`
- `ROOT_PACKAGE_DELETION_ALLOWED`
- `LIVE_TRADING_ALLOWED_BY_THIS_MODULE`
- `ORDER_ROUTING_ENABLED_BY_THIS_MODULE`
- `EXTERNAL_ORDER_SUBMISSION_PERFORMED`

## Validation

Step257 adds tests for:

- live executor `NotImplementedError` behavior;
- testnet default skipped behavior;
- testnet enabled-path `NotImplementedError` behavior;
- recovery query stub behavior;
- absence of canonical `live_executor.py` and `testnet_executor.py` files;
- exact `missing_canonical_module_count == 2`;
- root package deletion still deferred;
- Step257 JSON report status `DEFERRED_EXECUTION_STUB_POLICY_LOCKED`.

## Next Step

Proceed to Step258 with Feature Store / ResearchSignal v2 integration work while keeping root execution package deletion on hold.
