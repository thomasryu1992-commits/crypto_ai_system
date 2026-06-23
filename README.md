# Crypto AI System - Step150 Spreadsheet-First Guarded Package

This package is a guarded crypto research + paper trading + live-shadow system.

## Current Status

This is **not** a live trading bot.

It is a Step150 package with:

- Spreadsheet-first operational storage
- Latest JSON cache
- Local CSV backup
- Spreadsheet retry queue
- Synthetic/fallback data trading block
- Data health checks
- Research scoring and decision engine
- Trading signal engine
- ATR stop loss with min/max BPS guard
- Position sizing by risk
- Conservative paper engine
- Time-based risk guard
- Research-trading bridge policy v2
- Order state machine
- Idempotency key and client order ID
- Retry/reconciliation policy scaffold
- Shadow-only order executor
- Testnet executor skeleton
- Live executor intentionally disabled
- Limited live readiness report
- Safety test suite
- Paper forward test runner

## Quick Start

```powershell
copy .env.example .env
python -m pip install -r requirements.txt
python run_step150_validation.py
```

## Main Commands

```powershell
python run_full_cycle.py
python run_operational_dry_run.py
python run_spreadsheet_sync.py
python run_limited_live_readiness_report.py
python run_step150_safety_tests.py
python run_step150_forward_test.py --iterations 7
python run_step150_validation.py
```

## Storage Policy

```text
Spreadsheet / local CSV = operational history
storage/latest/*.json = latest state cache
storage/backup/spreadsheet/*.csv = local backup
storage/queue/spreadsheet_retry_queue.jsonl = retry queue
storage/logs/event_log.jsonl = event log
```

## Safety

Real exchange orders are blocked by default. The live executor raises `NotImplementedError`.
Testnet execution is also guarded until `ENABLE_TESTNET_ORDERS=true` and signed order logic is explicitly implemented.
