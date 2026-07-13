# Step244 v5 Canonical Port Patch Batch 1

## Purpose

Step244 applies the first small canonical port batch from the Step243 plan.

## Ported Modules

- `execution.retry_policy` → `crypto_ai_system.execution.retry_policy`
- `trading.atr` → `crypto_ai_system.trading.atr`

## Import Rewrite Scope

Only `tests/test_step150_safety.py` is rewritten for this batch:

- `from execution.retry_policy import classify_exchange_error`
- `from trading.atr import stop_distance_bps_from_atr`

become:

- `from crypto_ai_system.execution.retry_policy import classify_exchange_error`
- `from crypto_ai_system.trading.atr import stop_distance_bps_from_atr`

## Not Changed

- Root packages are not deleted.
- Root packages are not converted to thin wrappers.
- Remaining manual mapping imports are not rewritten.
- Paper execution, adapter routing, external API calls, Telegram real sends, and live trading remain disabled.

## Expected Result

- Direct root import count decreases from 25 to 23.
- Canonical port group count decreases from 11 to 9.
- Batch 1 ported modules no longer appear in the canonical port plan.
