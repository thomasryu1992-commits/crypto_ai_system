# Crypto AI System KB v2 - Full Repackaged Inventory

This package consolidates the work through Step 53.

## Included Step Scope

- Step 29~32: Paper Watch / Paper Position / TP-SL / Paper Performance
- Step 37~39: Setup Performance / Setup Weight / Setup Decision Gate / Disabled Setup blocking
- Step 40~43: Bot State / Trading Cycle / Telegram Alert / Forward Test
- Step 44~46: Mock Exchange / Risk Manager / Order Executor
- Step 47: Trading Bot ↔ Order Executor Bridge
- Step 48: Risk Manager bridge exception for linked paper position mock orders
- Step 49: Execution Reconciliation Manager
- Step 50: Full System Regression Test
- KB v2: `.raw/` and `wiki/` separation, `hot.md`, `index.md`, `log.md`, `source/entity/concept/scenario/report`, and KB lint
- Step 52: Real Market Data Ingestion v1 using Coinalyze + Market Snapshot Builder
- Step 53: Spreadsheet Export / optional Google Sheets Sync restoration

## Important Commands

```powershell
python run_full_regression_test.py
python test_coinalyze_connection.py
python -m data_collector_bot.real_market_data_collector
python -m knowledge_engine.market_snapshot_builder
python run_research_cycle.py
python run_trading_cycle.py
python run_spreadsheet_sync.py
python run_full_cycle.py
```

## Safety Defaults

```env
LIVE_TRADING_ENABLED=false
EXCHANGE_MODE=MOCK
EXCHANGE_ORDER_ENABLED=false
ORDER_EXECUTOR_INTEGRATION_ENABLED=false
GOOGLE_SHEETS_ENABLED=false
```

This package still does not execute live exchange orders.

## Step 54 Update

- Removed legacy fixed current price usage from runtime flow.
- Replaced strategy `DEFAULT_*` env keys with `FALLBACK_*` keys.
- Added `ALLOW_SYNTHETIC_MARKET_CONTEXT` and `SYNTHETIC_CURRENT_PRICE` for local tests only.
- Updated research cycle so market price comes from `storage/market_context.json`, normally created by real market data ingestion and market snapshot builder.
- Verified `python run_full_regression_test.py` passes after the change.
