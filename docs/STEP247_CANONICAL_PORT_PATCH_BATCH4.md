# Step247 v5 Canonical Port Patch Batch 4

## Purpose

Step247 applies the fourth canonical port batch.

## Ported Module

- `trading.paper_engine` → `crypto_ai_system.trading.paper_engine`

## Support Module

- `trading.position_sizing` → `crypto_ai_system.trading.position_sizing`

## Safety Rule

The canonical paper engine remains paper-only.

It must not enable live trading or submit exchange orders.

## Import Rewrite Scope

Only these files are rewritten for this batch:

- `run_paper_regression_test.py`
- `tests/test_step130_safety.py`
- `tests/test_step150_safety.py`

## Not Changed

- Root packages are not deleted.
- Root packages are not converted to thin wrappers.
- Remaining manual mapping imports are not rewritten.
- Paper execution enablement, adapter routing, external API calls, Telegram real sends, and live trading remain disabled.

## Expected Result

- Direct root import count decreases from 18 to 15.
- Canonical port group count decreases from 7 to 6.
- HIGH priority port group count decreases from 1 to 0.
