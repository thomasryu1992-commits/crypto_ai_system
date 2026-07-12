# Step Map — Consolidated Step1~157E

This file maps the earlier system concepts into the current consolidated package.

## Foundation

- Config/env loading: `src/crypto_ai_system/config.py`
- Safety flags: `src/crypto_ai_system/execution/safety.py`
- Storage paths: `src/crypto_ai_system/storage/paths.py`
- JSON latest state: `src/crypto_ai_system/storage/latest.py`
- JSONL event log: `src/crypto_ai_system/storage/jsonl.py`
- CSV spreadsheet backup: `src/crypto_ai_system/storage/csv_backup.py`
- Retry queue seam: `src/crypto_ai_system/storage/retry_queue.py`
- Spreadsheet writer seam: `src/crypto_ai_system/storage/spreadsheet_writer.py`

## Data Layer

- Extended adapter: `src/crypto_ai_system/data/extended_client.py`
- Exchange abstraction: `src/crypto_ai_system/data/exchange_adapter.py`
- Symbol mapping: `src/crypto_ai_system/data/symbol_mapper.py`
- Coinalyze seam: `src/crypto_ai_system/data/coinalyze_client.py`
- Market collection: `src/crypto_ai_system/data/collectors.py`
- Raw data collection: `src/crypto_ai_system/data/raw_data_collector.py`
- Raw data persistence: `src/crypto_ai_system/storage/raw_store.py`

## Research Bot

- Research bot: `src/crypto_ai_system/research/research_bot.py`
- Raw-to-score pipeline: `src/crypto_ai_system/research/raw_score_pipeline.py`
- Daily report renderer: `src/crypto_ai_system/research/report_renderer.py`
- Score engine: `src/crypto_ai_system/analysis/score_engine.py`
- Market condition analyzer: `src/crypto_ai_system/analysis/market_condition.py`
- Scenario builder: `src/crypto_ai_system/analysis/scenario_builder.py`

## Trading System

- Research score compatibility layer: `src/crypto_ai_system/strategy/research_score.py`
- Entry policy: `src/crypto_ai_system/strategy/entry_policy.py`
- Exit policy: `src/crypto_ai_system/strategy/exit_policy.py`
- Risk sizing: `src/crypto_ai_system/strategy/risk.py`
- Trading bot: `src/crypto_ai_system/trading/trading_bot.py`
- Signal bridge: `src/crypto_ai_system/trading/signal.py`
- Order state machine: `src/crypto_ai_system/trading/order_state_machine.py`
- Paper watch manager: `src/crypto_ai_system/paper/paper_watch_manager.py`

## Backtest / Parameter Sweep

- Backtest engine: `src/crypto_ai_system/backtest/engine.py`
- Metrics: `src/crypto_ai_system/backtest/metrics.py`
- Parameter sweep: `src/crypto_ai_system/backtest/parameter_sweep.py`

## Extended Testnet Preparation

- Dry-run order payload: `src/crypto_ai_system/execution/extended_order_builder.py`
- Idempotency key: `src/crypto_ai_system/execution/idempotency.py`

Actual signed testnet orders belong to Step159E and are intentionally not enabled in this Step157E package.
