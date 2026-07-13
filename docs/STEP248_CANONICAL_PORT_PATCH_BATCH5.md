# Step248 v5 Medium Priority Canonical Port Batch 1

## Purpose

Step248 applies the first MEDIUM-priority canonical port batch.

## Ported Module

- `execution.order_executor` → `crypto_ai_system.execution.order_executor`

## Safety Rule

The canonical order executor remains guarded/review-only.

It must not enable live trading, adapter routing, or external order submission.

## Import Rewrite Scope

Only these files are rewritten for this batch:

- `run_full_cycle.py`
- `test_mock_exchange.py`
- `test_order_executor.py`
- `trading_bot/order_executor_bridge.py`

## Compatibility Note

`trading_bot/order_executor_bridge.py` expected `execute_order_with_risk_check`. The legacy root module did not export this symbol. Step248 adds a canonical review-only compatibility function that always blocks external execution and preserves metadata for audit.

## Not Changed

- Root packages are not deleted.
- Root packages are not converted to thin wrappers.
- Remaining manual mapping imports are not rewritten.
- Paper execution enablement, adapter routing, external API calls, Telegram real sends, and live trading remain disabled.

## Expected Result

- Direct root import count decreases from 15 to 11.
- Canonical port group count decreases from 6 to 5.
