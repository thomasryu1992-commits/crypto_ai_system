# Step254 v5 Missing Canonical Module Disposition Plan

## Purpose

Step254 classifies the remaining `CANONICAL_MODULE_MISSING` root modules after Step253.

## Disposition Types

- `PORT_TO_CANONICAL`
- `KEEP_EXPLICIT_LEGACY_COMPATIBILITY`
- `RETIRE_OR_DEPRECATE`

## Result

Step254 is plan-only.

It does not port modules, delete root packages, or convert additional wrappers.

## Expected Classification

- `PORT_TO_CANONICAL`: 8
- `KEEP_EXPLICIT_LEGACY_COMPATIBILITY`: 2
- `RETIRE_OR_DEPRECATE`: 0

## Safety

Execution-sensitive modules must remain disabled/review-only. Step254 must not enable:

- paper execution
- order execution
- adapter routing
- external API calls
- Telegram real sends
- live trading

## Next Step

Step255 should port the execution support modules first:

- `execution.order_models`
- `execution.order_state`
- `execution.mock_exchange`
- `execution.exchange_router`
