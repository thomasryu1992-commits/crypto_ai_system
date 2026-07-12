# Step251 v5 Trading Cycle Canonical Port Batch

## Purpose

Step251 ports the final remaining root import group to the canonical package.

## Ported Module

- `trading.trading_cycle` → `crypto_ai_system.trading.trading_cycle`

## Support Module

- `trading.signal_engine` → `crypto_ai_system.trading.signal_engine`

## Safety Rule

Trading cycle remains paper/shadow decision-only.

It must not enable order execution, external order submission, adapter routing, or live trading.

## Import Rewrite Scope

Only these files are rewritten for this batch:

- `run_full_cycle.py`
- `run_trading_cycle.py`
- `trading_bot/trading_app.py`

## Expected Result

- Direct root import count decreases from 3 to 0.
- Canonical port group count decreases from 1 to 0.
- Root direct imports are fully retired.
