# Step246 v5 Canonical Port Patch Batch 3

## Purpose

Step246 applies the third canonical port batch.

## Ported Module

- `execution.live_guard` → `crypto_ai_system.execution.live_guard`

## Safety Rule

This module remains readiness-check only.

It must not enable or submit live orders.

## Import Rewrite Scope

Only these files are rewritten for this batch:

- `run_live_readiness_check.py`
- `run_step150_validation.py`
- `tests/test_step130_safety.py`

## Not Changed

- Root packages are not deleted.
- Root packages are not converted to thin wrappers.
- Remaining manual mapping imports are not rewritten.
- Paper execution, adapter routing, external API calls, Telegram real sends, and live trading remain disabled.

## Expected Result

- Direct root import count decreases from 21 to 18.
- Canonical port group count decreases from 8 to 7.
- Batch 3 ported module no longer appears in the canonical port plan.
